import os
import gzip
import json
import re

import numpy as np
import pdb

from collections import defaultdict
from scipy.sparse import csr_matrix

from .algorithms import query_vector, random_walk_with_restart
from .path import DBPEDIA_DATA_DIR, YAGO_DATA_DIR, METAQA_DATA_DIR, ENCODING

FREEBASE_DATA_DIR = ''

class KnowledgeGraph(object):

    def __init__(self):
        """A KG is a set of entities E, a set of relationships R,
        and a set of triples E x R x E."""
        # 实体集合
        self.entities_ = set()
        # 实体关系集合
        self.relationships_ = set()
        # 三元组集合
        self.triples_ = {}
        # 三元组数量
        self.number_of_triples_ = 0

        # Map entities to numeric IDs
        self.eid_ = 0
        self.rid_ = 0
        self.entity_id_ = {}
        self.id_entity_ = {}
        self.relation_id_ = {}
        self.id_relation_ = {}
        self.entities_to_relation_ = {}

        self.name_ = None

        # for efficiency
        self.csr_matrix_ = None
        self.csr_matrix_T_ = None
        self.csr_matrix_indirect_ = None
        self.csr_matrix_heterogeneous_ = None
        self.csr_matrix_heterogeneous_indirect_ = None
        self.transition_matrix_ = None
        self.csr_matrix_indirect_heat_ = None

        self.triples_by_relation_id_ = {}
        

    def name(self):
        return self.name_

    def entities(self):
        """
        :return entities: all entities in the KG
        """
        return self.entities_

    def relationships(self):
        """
        :return relationships: all relations in the KG
        """
        return self.relationships_

    def triples(self):
        """
        :return triples: {(e1, r, e2) triples}

        Note that this method is linear in the number of triples
        in the KG because it has to create a flat set of triples.
        """
        triples = set()
        for e1 in self.triples_:
            for r in self.triples_[e1]:
                for e2 in self.triples_[e1][r]:
                    triples.add((e1, r, e2))
        return triples

    def number_of_entities(self):
        """
        :return n_entities: number of entities in the KG
        """
        return len(self.entities_)

    def number_of_relationships(self):
        """
        :return n_relations: number of relations in the KG
        """
        return len(self.relationships_)

    def number_of_triples(self):
        """
        :return n_triples: number of triples in the KG
        """
        return self.number_of_triples_

    def has_entity(self, entity):
        """
        :param entity: str
        :return has_entity: True if KG contains this entity
        """
        return entity in self.entities_

    def has_relationship(self, relationship):
        """
        :param relationship: str
        :return has_relationship: True if KG contains this relationship
        """
        return relationship in self.relationships_

    def __getitem__(self, entity):
        """
        :param entity: str
        :return d: dict of set of {relation : entities}
        """
        return self.triples_[entity]

    def __contains__(self, entity):
        """
        :param entity: str
        :return has_entity: True if KG contains this head entity
        """
        return entity in self.triples_

    # 判断有无三元组
    def has_triple(self, triple):
        """
        :param triple: (e1, r, e2)
        :return has_triple: True if KG contains this triple
        """
        e1, r, e2 = triple
        return e1 in self.triples_ and r in self.triples_[e1] and e2 in self.triples_[e1][r]
    
    def find_triple_by_entities_indirect(self, e1, e2):
        value1 = self.csr_matrix_heterogeneous()[e1, e2]
        if value1 != 0:
            return (e1, value1, e2)
        value2 = self.csr_matrix_heterogeneous()[e2, e1]
        if value2 != 0:
            return (e2, value2, e1)
        return None

    def add_triple(self, triple):
        """
        :param triple: (e1, r, e2) triple
        """
        e1, r, e2 = triple
        if not self.has_triple(triple):
            self.number_of_triples_ += 1
            
            # Record new entities
            for entity in (e1, e2):
                if not self.has_entity(entity):
                    self.entity_id_[entity] = self.eid_
                    self.id_entity_[self.eid_] = entity
                    self.entities_.add(entity)
                    self.eid_ += 1

            # record new relation
            if not self.has_relationship(r):
                self.relation_id_[r] = self.rid_
                self.id_relation_[self.rid_] = r
                self.relationships_.add(r)
                self.rid_ += 1


            if e1 not in self.triples_:
                self.triples_[e1] = {}
            if r not in self.triples_[e1]:
                self.triples_[e1][r] = set()
            self.triples_[e1][r].add(e2)

            if e1 not in self.entities_to_relation_:
                self.entities_to_relation_[e1] = {}
            if e2 not in self.entities_to_relation_[e1]:
                self.entities_to_relation_[e1][e2] = set()
            self.entities_to_relation_[e1][e2].add(r)

    # 实体转化为id
    def entity_id(self, entity):
        """
        :param entity: str label
        :return eid: entity integer ID
        """
        return self.entity_id_[entity]

    def id_entity(self, eid):
        """
        :param eid: entity integer ID
        :return entity: str label
        """
        return self.id_entity_[eid]
    
    def relation_id(self, r):
        return self.relation_id_[r]
    
    def id_relation(self, rid):
        return self.id_relation_[rid]
    
    def csr_matrix(self):
        if self.csr_matrix_ is None:
            self.csr_matrix_ = self.calc_csr_matrix()
        return self.csr_matrix_

    def calc_csr_matrix(self):
        """
        :return A: scipy sparse CSR adjacency matrix
        """
        row, col, data = [], [], []
        for e1 in self.triples_:
            for r in self.triples_[e1]:
                for e2 in self.triples_[e1][r]:
                    """
                    用下面的例子A喜欢B，B喜欢C，C喜欢D，D喜欢C，E喜欢D
                    下面这个：
                    row:{0,1,2,3,4}
                    col:{1,2,3,2,3}
                    data:{1,1,1,1,1,1,1,1,1,1}
                    """
                    row.append(self.entity_id(e1))
                    col.append(self.entity_id(e2))
                    data.append(1)

        n = self.number_of_entities()
        """
        下面这个得到的数组会是
        (A) 0 1 0 0 0
        (B) 0 0 1 0 0
        (C) 0 0 0 1 0
        (D) 0 0 1 0 0
        (E) 0 0 0 1 0
        我觉得这个理解一下就是一个有向图。坐标表示两个实体，数值表示是否有某种关系。
        有向图你可以理解为：实体A->喜欢->实体B，但是实体B倒着不能追溯回去
        此时你读纵坐标（坐标系的啊,看上面横着的字母），可以理解为“我是A，通过我能找到B（横坐标1号位表示B，1号位不空表示可达），我是B，通过我能找到C”
        """
        return csr_matrix(
                (np.array(data), (np.array(row), np.array(col))),
                shape=(n,n))
    
    def csr_matrix_T(self):
        if self.csr_matrix_T_ is None:
            """
            根据上面那个矩阵进行转置
            (A) 0 0 0 0 0
            (B) 1 0 0 0 0
            (C) 0 1 0 1 0
            (D) 0 0 1 0 1
            (E) 0 0 0 0 0
            此时你读纵坐标（坐标系的啊,看上面横着的字母），可以理解为“我是B，通过A能找到我（横坐标0号位表示A，0号位不空表示可达）”
            """
            self.csr_matrix_T_ = self.csr_matrix().transpose()
        return self.csr_matrix_T_
    
    def csr_matrix_indirect(self):
        if self.csr_matrix_indirect_ is None:
            self.csr_matrix_indirect_ = self.calc_csr_matrix_indirect()
        return self.csr_matrix_indirect_

    def calc_csr_matrix_indirect(self):
        """
        这里就是把上面俩矩阵加一起
        0 1 0 0 0   0 0 0 0 0
        0 0 1 0 0   1 0 0 0 0
        0 0 0 1 0   0 1 0 1 0
        0 0 1 0 0   0 0 1 0 1
        0 0 0 1 0   0 0 0 0 0
        得到
        0 1 0 0 0
        1 0 1 0 0
        0 1 0 2 0
        0 0 2 0 1
        0 0 0 1 0
        理解这个矩阵的方法我觉得应该是忽略掉有向图的方向性。因为按照刚才那个可达不可达会发现A能找到B，B也能找到A了。
        如果是1说明本身是单向寻找的，现在无法单看这个矩阵无法知道是哪个实体找的谁，如果是2说明本身两个实体就是互相可达的。也不需要知道方向了
        所以，这个A+A_T的方式可以把有向图转化成无向图
        """
        return self.csr_matrix() + self.csr_matrix_T()
    #  构建矩阵，外部算法调用的是这个
    def csr_matrix_indirect_heat(self):
        if self.csr_matrix_indirect_heat_ is None:
            self.csr_matrix_indirect_heat_ = self.calc_csr_matrix_indirect_heat()
        return self.csr_matrix_indirect_heat_
    # 借助这个方法构建矩阵
    def calc_csr_matrix_indirect_heat(self):
        """
        :return A: scipy CSR column-stochastic transition matrix
        """
        # Create the degree matrix
        row, col, data = [], [], []
        for e1 in self.triples_:
            for r in self.triples_[e1]:
                for e2 in self.triples_[e1][r]:
                    """
                    每经历一个三元组就会像下面这样添加进去
                    这里面的entity_id其实就是实体被添加到图谱中的编号，从0开始编号的
                    假如添加了A喜欢B，B喜欢C，C喜欢D。这三个三元组。会有四个实体添加进去，编号分别是0123。
                    
                    分别看一下每次循环的效果
                    row「0，1」
                    col「0，1」
                    data「1，1」
                    
                    row「0，1，1，2」
                    col「0，1，1，2」
                    data「1，1，1，1」
                    
                    row「0，1，1，2, 2, 3」
                    col「0，1，1，2, 2, 3」
                    data「1，1，1，1, 1, 1」
                    """
                    row.append(self.entity_id(e1))
                    col.append(self.entity_id(e1))
                    data.append(1)
                    row.append(self.entity_id(e2))
                    col.append(self.entity_id(e2))
                    data.append(1)
        # 这个是实体数,以上面为例就是4
        n = self.number_of_entities()
        """
        np.array是list转数组。csr_matrix接受的参数是数组
        csr_matrix函数产生的结果是一种“只存非零元素”的矩阵表示方式：只存非0值和这个值的位置。
        csr_matrix函数的作用是把 (row[i], col[i]) 位置赋值为 data[i]
        row  = [0,1,1,2,2,3]
        col  = [0,1,1,2,2,3]
        data = [1,1,1,1,1,1]
        看作
        （row，col） = {[0,0], [1,1][1,1],[2,2][2,2],[3,3]}
        会得到一个矩阵是
        1 0 0 0
        0 2 0 0
        0 0 2 0 
        0 0 0 1
        
        假如再添加两个三元组分别是D喜欢C,E喜欢D，
        那么row，col，data重新理一下分别是
        [0,1,1,2,2,3,3,2,4,3]
        [0,1,1,2,2,3,3,2,4,3]
        [1,1,1,1,1,1,1,1,1,1]
        row, col = [00][11][11][22][22][33][33][22][44][33]
        矩阵就是
        1 0 0 0 0
        0 2 0 0 0
        0 0 3 0 0
        0 0 0 2 0
        0 0 0 0 1
        可以理解一下就是，横坐标你可以理解为某个元素，然后这一列中有数字的那里是几就说明有几个实体和他相关，A与B相关1，B与A，C相关3，以此类推
        相当于下图
        A B C D E
        1 0 0 0 0
        0 2 0 0 0
        0 0 3 0 0
        0 0 0 2 0
        0 0 0 0 1
        综上，下面计算的这个D值 = csr_matrix( (np.array(data), (np.array(row), np.array(col))), shape=(n,n)表示每个实体在知识图谱三元组中的出现频次，也可以说是参与到了多少对关系中
        """
        D = csr_matrix(
                (np.array(data), (np.array(row), np.array(col))),
                shape=(n,n))
        # 得到 D⁻¹
        D1 = D.copy().astype(float)
        for i in range(n):
            va = D[i, i]
            if va != 0:
                D1[i, i] = 1/D[i, i]
        """
        得到的D1（一定是对角矩阵），用上面的例子就是
        1   0   0   0   0
        0 1/2  0   0   0
        0   0 1/3  0   0
        0   0   0 1/2  0
        0   0   0   0   1
        我感觉是把出现的频率换成了一个比重一样的东西（我的理解是，从这个实体出发走向每个和他相关实体的概率，倒数，和几个实体相连，那么到一个实体的概率就是几分之一）
        """
        """
        下面前半段的这个函数的结果如下（可以跳进这个函数里面看执行步骤，里面我写了注释）简称MM矩阵吧
        0 1 0 0 0
        1 0 1 0 0
        0 1 0 2 0
        0 0 2 0 1
        0 0 0 1 0
        MM × D1 = 第 j 列 × D1[j][j] （这个过程我理解的是某个实体到其他实体的概率）
        
        得到的矩阵为
        0   1/2   0     0     0
        1   0     1/3   0     0
        0   1/2   0     2/3   0
        0   0     2/3   0     1
        0   0     0     1/3   0
        找到A，和他相关的元素为B，概率为1
        找到B，和他相关的元素为A，C，概率各自为1/2
        找到C，相关B的概率是1/3，相关D的概率是2/3
        找到D，相关C的概率是2/3，相关E的概率是1/3
        找到E，相关D的概率是1
        """
        return self.csr_matrix_indirect().astype(float) * D1

    def transition_matrix(self):
        if self.transition_matrix_ is None:
            self.transition_matrix_ = self.calc_transition_matrix()
        return self.transition_matrix_

    def calc_transition_matrix(self):
        """
        :return A: scipy CSR column-stochastic transition matrix
        """
        # Create the degree matrix
        row, col, data = [], [], []
        for e1 in self.triples_:
            for r in self.triples_[e1]:
                for e2 in self.triples_[e1][r]:
                    row.append(self.entity_id(e1))
                    col.append(self.entity_id(e1))
                    data.append(1)
        n = self.number_of_entities()
        D = csr_matrix(
                (1 / np.array(data), (np.array(row), np.array(col))),
                shape=(n,n))
        D1 = D.copy()
        for i in range(n):
            va = D[i, i]
            if va != 0:
                D1[i, i] = 1/D[i, i]

        return self.csr_matrix().transpose() * D1
    
    # heterogeneous matrices
    def csr_matrix_heterogeneous(self):
        if self.csr_matrix_heterogeneous_ is None:
            self.csr_matrix_heterogeneous_ = self.calc_csr_matrix_heterogeneous()
        return self.csr_matrix_heterogeneous_

    def calc_csr_matrix_heterogeneous(self):
        """
        :return A: scipy sparse CSR adjacency matrix
        """
        row, col, data = [], [], []
        for e1 in self.triples_:
            for r in self.triples_[e1]:
                for e2 in self.triples_[e1][r]:
                    row.append(self.entity_id(e1))
                    col.append(self.entity_id(e2))
                    data.append(self.relation_id(r))

        n = self.number_of_entities()
        return csr_matrix(
                (np.array(data), (np.array(row), np.array(col))),
                shape=(n,n))
    
    def triples_by_relation_id(self, relation_id):
        relation = self.id_relation(relation_id)
        if relation_id not in self.triples_by_relation_id_:
            self.triples_by_relation_id_[relation_id] = []
            for triple in self.triples():
                if triple[1] == relation:
                    self.triples_by_relation_id_[relation_id].append((self.entity_id(triple[0]), relation_id, self.entity_id(triple[2])))
        return self.triples_by_relation_id_[relation_id]

    def reset(self):
        """Sets all values to 0"""
        self.entity_value_ = defaultdict(float)
        self.triple_value_ = defaultdict(float)

    def entity_value(self, entity):
        """
        :param entity: str
        :return value: entity float value
        """
        return self.entity_value_[entity]

    def triple_value(self, triple):
        """
        :param triple: (e1, r, e2) triple
        :return value: triple float value
        """
        return self.triple_value_[triple]

    def model_user_pref(self, query_log, power=1):
        """
        :param query_log: list of queries as dicts
        :param power: number of terms in Taylor expansion
        """
        self.reset()
        # Perform random walk on the KG
        x = query_vector(self, query_log)
        M = self.transition_matrix()
        x = random_walk_with_restart(M, x, power=power)
        # x /= np.sum(x)

        # Store entity and triple values
        for eid, val in enumerate(x):
            entity = self.id_entity(eid)
            self.entity_value_[entity] = np.log(val + 1)

        for e1 in self.triples_:
            for r in self.triples_[e1]:
                for e2 in self.triples_[e1][r]:
                    triple = (e1, r, e2)
                    eid1, eid2 = self.entity_id(e1), self.entity_id(e2)
                    self.triple_value_[triple] = np.log(x[eid1] * x[eid2] + 1)

    def query_dir(self):
        raise NotImplementedError

    def topic_dir(self):
        raise NotImplementedError

    def mid_dir(self):
        raise NotImplementedError

    def topics(self):
        raise NotImplementedError

    def topic_mids(self):
        raise NotImplementedError

    def entity_names(self):
        raise NotImplementedError

class Freebase(KnowledgeGraph):

    def __init__(self, rdf_gz='webqsp-filtered-relations-freebase-rdfs.gz',
                 entity_names='all_entities.tsv', query_dir='queries/',
                 topic_dir='by-topic/', mid_dir='by-mid/'):
        """
        :param rdf_gz: filename of Freebase dump
        :param entity_names: mapping from MIDs to labels
        :param query_dir: directory where queries are saved as json
        :param topic_dir: directory where lists of query IDs by topic are stored
        :param mid_dir: directory where lists of query IDs by MID are stored
        """
        super().__init__()
        self.name_ = 'Freebase'

        self.rdf_gz_ = os.path.join(FREEBASE_DATA_DIR, rdf_gz)
        self.entity_names_ = os.path.join(FREEBASE_DATA_DIR, entity_names)
        self.query_dir_ = os.path.join(FREEBASE_DATA_DIR, query_dir)
        self.topic_dir_ = os.path.join(FREEBASE_DATA_DIR, topic_dir)
        self.mid_dir_ = os.path.join(FREEBASE_DATA_DIR, mid_dir)

    def has_fb_prefix(self, s):
        return s.startswith('<f_')

    def is_entity(self, s):
        return s.startswith('m.') or s.startswith('g.') or \
                s.startswith('<f_m.') or s.startswith('<f_g.')

    def strip_prefix(self, s):
        return s[3:-1]

    def query_dir(self):
        return self.query_dir_

    def topic_dir(self):
        return self.topic_dir_

    def mid_dir(self):
        return self.mid_dir_

    def topics(self):
        return [fname.split('.')[0] for fname in os.listdir(self.topic_dir_)]

    def topic_mids(self):
        return [fname[:-5] for fname in os.listdir(self.mid_dir_)]

    def entity_names(self):
        entity_names = {}
        with open(self.entity_names_, 'r') as f:
            next(f)
            for line in f:
                mid, name = line.rstrip().split('\t')
                entity_names[mid] = name
        return entity_names

    def load(self, head=None, strip=True):
        with gzip.open(self.rdf_gz_, 'rt') as f:
            for line in f:
                fact = tuple(line.rstrip().split('\t')[:-1])
                e1, r = fact[:2]
                e2 = ' '.join(fact[2:])

                if strip:
                    e1 = self.strip_prefix(e1) if self.has_fb_prefix(e1) else e1
                    e2 = self.strip_prefix(e2) if self.has_fb_prefix(e2) else e2
                    r = self.strip_prefix(r) if self.has_fb_prefix(r) else r

                triple = (e1, r, e2)
                self.add_triple(triple)

                if self.number_of_triples() == head:
                    return

# 继承Knowledge
class YAGO(KnowledgeGraph):

    def __init__(self, rdf_gz='yagoFacts.gz', query_dir='final/', mid_dir='by-mid/'):
        """
        :param rdf_gz: YAGO dump
        :param query_dir: directory where queries are saved as json
        :param mid_dir: directory where lists of query IDs by MID are stored
        """
        super().__init__()
        self.name_ = 'YAGO'

        self.YAGO_DATA_DIR_query = YAGO_DATA_DIR + '/queries'
        self.initial_query_dir = query_dir
        self.initial_mid_dir = mid_dir
        self.user_dir = None

        self.rdf_gz_ = os.path.join(YAGO_DATA_DIR, rdf_gz)
        self.query_dir_ = os.path.join(self.YAGO_DATA_DIR_query, query_dir)
        self.mid_dir_ = os.path.join(self.YAGO_DATA_DIR_query, mid_dir)

    def is_entity(self, s):
        """Only use YAGO file with entities, no values"""
        return True

    def strip(self, s):
        return re.sub(r'([^\s\w]|)+', '', s)

    def query_dir(self):
        return self.query_dir_

    def mid_dir(self):
        return self.mid_dir_
    
    def update_user(self, user_number):
        # 更新用户目录
        USER_DIR = os.path.join(self.YAGO_DATA_DIR_query, 'user' + str(user_number))
        self.user_dir = USER_DIR
        self.query_dir_ = os.path.join(USER_DIR, self.initial_query_dir)
        self.mid_dir_ = os.path.join(os.path.join(self.YAGO_DATA_DIR_query, 'user' + str(user_number)), self.initial_mid_dir)

        # 检查目录存在
        CHECK_FOLDER = os.path.isdir(USER_DIR)

        # If folder doesn't exist, then create it.
        if not CHECK_FOLDER:
            os.makedirs(USER_DIR)

        CHECK_QUERY_FOLDER = os.path.isdir(self.query_dir_)
        if not CHECK_QUERY_FOLDER:
            os.makedirs(self.query_dir_)

        CHECK_MID_FOLDER = os.path.isdir(self.mid_dir_)
        if not CHECK_MID_FOLDER:
            os.makedirs(self.mid_dir_)

    def topic_mids(self):
        return [fname[:-5] for fname in os.listdir(self.mid_dir_)]

    def entity_names(self):
        return { entity : entity for entity in self.entities() }

    def load(self, head=None, strip=True):
        with gzip.open(self.rdf_gz_, 'rt', encoding = ENCODING) as f:
            for line in f:
                fact = tuple(line.rstrip().split('\t')[1:])
                e1, r = fact[:2]
                e2 = ' '.join(fact[2:])

                if strip:
                    e1 = self.strip(e1)
                    e2 = self.strip(e2)
                    r = self.strip(r)

                if not e1 or not e2:
                    continue

                triple = (e1, r, e2)
                self.add_triple(triple)

                if self.number_of_triples() == head:
                    return


class DBPedia(KnowledgeGraph):

    def __init__(self, rdf_gz='facts.gz', query_dir='final/', mid_dir='by-mid/'):
        """
        :param rdf_gz: YAGO dump
        :param query_dir: directory where queries are saved as json
        :param mid_dir: directory where lists of query IDs by MID are stored
        """
        super().__init__()
        self.DBPEDIA_DATA_DIR_query = DBPEDIA_DATA_DIR + '/queries'
        self.initial_query_dir = query_dir
        self.initial_mid_dir = mid_dir
        self.user_dir = None

        self.name_ = 'DBPedia'

        self.rdf_gz_ = os.path.join(DBPEDIA_DATA_DIR, rdf_gz)
        self.query_dir_ = os.path.join(self.DBPEDIA_DATA_DIR_query, query_dir)
        self.mid_dir_ = os.path.join(self.DBPEDIA_DATA_DIR_query, mid_dir)

    def is_entity(self, s):
        return s.startswith('<') and s.endswith('>')

    def query_dir(self):
        return self.query_dir_

    def mid_dir(self):
        return self.mid_dir_
    
    def update_user(self, user_number):
        USER_DIR = os.path.join(self.DBPEDIA_DATA_DIR_query, 'user' + str(user_number))
        self.user_dir = USER_DIR
        self.query_dir_ = os.path.join(USER_DIR, self.initial_query_dir)
        self.mid_dir_ = os.path.join(os.path.join(self.DBPEDIA_DATA_DIR_query, 'user' + str(user_number)), self.initial_mid_dir)
        
        CHECK_FOLDER = os.path.isdir(USER_DIR)

        # If folder doesn't exist, then create it.
        if not CHECK_FOLDER:
            os.makedirs(USER_DIR)

        CHECK_QUERY_FOLDER = os.path.isdir(self.query_dir_)
        if not CHECK_QUERY_FOLDER:
            os.makedirs(self.query_dir_)

        CHECK_MID_FOLDER = os.path.isdir(self.mid_dir_)
        if not CHECK_MID_FOLDER:
            os.makedirs(self.mid_dir_)

    def topic_mids(self):
        return [fname[:-5] for fname in os.listdir(self.query_dir_)]

    def entity_names(self):
        return { entity : entity for entity in self.entities() }

    def load(self, head=None, strip=True):
        with gzip.open(self.rdf_gz_, 'rt', encoding = ENCODING) as f:
            for line in f:
                fact = line.rstrip('\n')[:-2].replace('/', '-').replace('<', '').replace('>', '').replace(':', '').replace('*', '').replace('%', '').split(' ')
                e1, r = fact[:2]
                e2 = ' '.join(fact[2:])

                if not e1 or not e2:
                    continue

                triple = (e1, r, e2)
                self.add_triple(triple)

                if self.number_of_triples() == head:
                    return
                


class MetaQA(KnowledgeGraph):
    
    def __init__(self, rdf_gz='kb.txt', query_dir='final/', mid_dir='by-mid/'):
        """
        :param rdf_gz: YAGO dump
        :param query_dir: directory where queries are saved as json
        :param mid_dir: directory where lists of query IDs by MID are stored
        """
        super().__init__()
        self.name_ = 'MetaQA'

        self.METAQA_DATA_DIR_query = METAQA_DATA_DIR + '/queries'

        self.initial_query_dir = query_dir
        self.initial_mid_dir = mid_dir
        self.user_dir = None

        self.rdf_gz_ = os.path.join(METAQA_DATA_DIR, rdf_gz)

        self.query_dir_ = os.path.join(self.METAQA_DATA_DIR_query, query_dir)
        self.mid_dir_ = os.path.join(self.METAQA_DATA_DIR_query, mid_dir)
        # 这玩意是个map，key是知识图谱元素中的关系，value是词
        self.relation_translate = {'has_tags': ['movie_to_tags', 'tag_to_movie'], 'starred_actors': ['movie_to_actor', 'actor_to_movie'], 'directed_by': ['movie_to_director', 'director_to_movie'], 'written_by': ['movie_to_writer', 'writer_to_movie'], 'release_year': ['movie_to_year'], 'has_imdb_votes': ['movie_to_imdbvotes'], 
                      'has_imdb_rating': ['movie_to_imdbrating'], 'in_language': ['movie_to_language'], 'has_genre': ['movie_to_genre']}

    def is_entity(self, s):
        return True
    
    def query_dir(self):
        return self.query_dir_

    def mid_dir(self):
        return self.mid_dir_
    
    def update_user(self, user_number):
        USER_DIR = os.path.join(self.METAQA_DATA_DIR_query, 'user' + str(user_number))
        self.user_dir = USER_DIR
        self.query_dir_ = os.path.join(USER_DIR, self.initial_query_dir)
        self.mid_dir_ = os.path.join(os.path.join(self.METAQA_DATA_DIR_query, 'user' + str(user_number)), self.initial_mid_dir)

        CHECK_FOLDER = os.path.isdir(USER_DIR)

        # If folder doesn't exist, then create it.
        if not CHECK_FOLDER:
            os.makedirs(USER_DIR)

        CHECK_QUERY_FOLDER = os.path.isdir(self.query_dir_)
        if not CHECK_QUERY_FOLDER:
            os.makedirs(self.query_dir_)

        CHECK_MID_FOLDER = os.path.isdir(self.mid_dir_)
        if not CHECK_MID_FOLDER:
            os.makedirs(self.mid_dir_)

    def topic_mids(self):
        return [fname[:-5] for fname in os.listdir(self.query_dir_)]
    
    def entity_names(self):
        return { entity : entity for entity in self.entities() }

    # 加载知识图谱的内容
    def load(self, head=None, strip=True):
        # 以只读的形式打开文件
        with open(self.rdf_gz_, 'r', encoding='utf-8') as f:
            # 遍历每一行读取成为一个数组吧
            for line in f:
                fact = tuple(line.rstrip().split('|'))
                # 分别表示数组中的三个元素：实体-关系-实体
                e1, r, e2 = fact

                if not e1 or not e2:
                    continue
                # 判断某个关系的valueList的长度是否为1
                if len(self.relation_translate[r]) == 1:
                    # 长度为一时构建三元组，把关系替换为map中的首个value并添加到三元组集合中
                    triple = (e1, self.relation_translate[r][0], e2)
                    self.add_triple(triple)
                else:
                    # 不为一的时候构建两个三元组，分别提取map中的两个value并添加到三元组集合中
                    triple1 = (e1, self.relation_translate[r][0], e2)
                    self.add_triple(triple1)
                    triple2 = (e2, self.relation_translate[r][1], e1)
                    self.add_triple(triple2)

                if self.number_of_triples() == head:
                    return

import numpy as np
import scipy.sparse as sp
from .base import KnowledgeGraph
from time import time
from .metrics import total_query_log_metrics, average_query_log_metrics
import logging
import random
from tqdm import tqdm
DETAILED_LOGGING = True
GAMMA = 0.5

class Summary(KnowledgeGraph):

    def __init__(self, KG):
        """
        :param KG: KnowledgeGraph
        """
        super().__init__()
        self.parent_ = KG

    def parent(self):
        return self.parent_

    def fill(self, triples, k):
        """
        :param triples: triples to add to summary
        :param k: limit
        """
        for triple in triples:
            if self.number_of_triples() >= k:
                return
            self.add_triple(triple)

    def add_entity(self, topic_mid):
        for entity in self.entities().copy():
            if self.parent().csr_matrix()[self.parent().entity_id_[entity], self.parent().entity_id_[topic_mid]] != 0: # exists a triple
                # find the relationship
                for r in self.parent().entities_to_relation_[entity][topic_mid]:
                    self.add_triple((entity, r, topic_mid))

            if self.parent().csr_matrix_T()[self.parent().entity_id_[entity], self.parent().entity_id_[topic_mid]] != 0: # exists a triple
                for r in self.parent().entities_to_relation_[topic_mid][entity]:
                    self.add_triple((topic_mid, r, entity))

        # in case self.entities() is empty
        self.entities_.add(topic_mid)

    
    def add_random_triple(self):
        e1 = random.choice(list(self.parent().triples_.keys()))
        r = random.choice(list(self.parent()[e1].keys()))
        e2 = random.choice(list(self.parent()[e1][r]))
        self.add_triple((e1, r, e2))


def Heat_Diffuse(heat, KG, query, d, csr_indirect_matrices): # adj matrix and heat
    # 全零向量，后面有用
    q = np.zeros(KG.number_of_entities())
    # 从查询参数中读取 parse 字段，这个查询参数就一个字典类型的数据，（对应 java 中的 hashmap。js 中我记得好像也叫字典，其实就是键值对集合）
    parse = query['Parse']
    # 从字典中取出实体（我觉得你打开这个文件看看可能更好理解/Users/zjh/code/python/APEX/PKG_EXP/MetaQA/queries/user0/final/q0.json）忽略前面的一堆，我复制的绝对路径，主要从 PKG 那个路径那里找就知道了
    topic_mid = parse['TopicEntityMid']
    # 从图谱中定位到这个实体的 id（代码写的太差了这里）
    topic_eid = KG.entity_id(parse['TopicEntityMid'])
    # 提取关系
    relation = parse['InferentialChain'][0]
    # 从图谱中取出结果——实体与关系对应的另外那个实体
    answers = KG[topic_mid][relation]
    # 用来存储答案实体对应的整数 ID，也可以理解为请求参数中实体的 id
    q[topic_eid] += 1
    # 答案的列 id 的集合
    answers_rid = np.zeros(len(answers), dtype = int)
    # 遍历答案集合
    for i, item in enumerate(answers):
        # 根据答案 id 修改对应的答案列 id 的值
        answers_rid[i] = KG.entity_id(item)
        # 这里是把答案的概率平均分，然后分配到实体的位置上，可以说是实体参加到每段关系的概率又赋值上去了
        q[answers_rid[i]] += 1/len(answers)
        """
        把 q[i]理解为被影响度（当成水来理解吧，水量）
        举个例子吧。
        我把倒水当做一次查询（理论上查询只涉及到两个实体，那就是两杯水）。把关系比作一个管道。
        有 A->B,A->C这两种关系，我把水倒入 A，满了才会进入 B，但是也可能流入 C。
        不在人为干预的情况下这两杯水会有一杯完全留在 A 里面，剩下 B，C 各留半杯水
        此时理解下来就是 q[0] = 1
        q[1] = 1/2
        q[2] = 1/2        
        """


    # 这里是图的扩散，首先复制 q 矩阵
    r = q.copy()
    """
    之前有说过 csrk = a^k M^k,忽略那个常数可以看作 csrk=M^k
    q[0] +=1
    q[1] +=1
    q[2] +=1
    那么下面这个q的计算 就相当于 q =M^k * q
    这个 csrk 之前也说过每个元素相当于查询时跳 k 步查询到某个元素的概率
    再理解一下，此时用乘法就相当于原先平均非配的概率改为了按比例分配
    所以此时的q 的含义就是某个实体最后接到了多少水（在本次查询中被影响到了多少）
    r 是走一步的影响+走两步的影响+走三步的影响。。。
    """
    for i in range(d):
        q = csr_indirect_matrices[i+1] * q
        r += q
    changed_index_list = []
    # 这里我不太理解，他抛弃了一些数，像是被影响量低的实体直接被他抛弃了，不太确定，先这样吧
    for i in range(len(r)):
        if r[i] != 0 and r[i] > 1e-3:
            changed_index_list.append(i)
        else:
            r[i] = 0
    r += heat

    return r, changed_index_list


def heat_decay_array(h, gamma, threshold = 1e-3):
    h = h * gamma
    for i in range(len(h)):
        if h[i] < threshold:
            h[i] = 0


def binary_find(index_list, changed_index, H):
    changed_value = H[changed_index]
    low = 0
    high = len(index_list) - 1
    mid = 0
    while high >= low:
        mid = (high + low)//2
        if H[index_list[mid]] < changed_value:
            high = mid - 1
        elif H[index_list[mid]] > changed_value:
            low = mid + 1
        else:
            if (index_list[mid] == changed_index):
                return mid
            else:
                mid_right = mid + 1
                mid_left = mid - 1
                while mid_right < len(index_list) and H[index_list[mid_right]] == changed_value:
                    if index_list[mid_right] == changed_index:
                        return mid_right
                    mid_right += 1
                while mid_left >= 0 and H[index_list[mid_left]] == changed_value:
                    if index_list[mid_left] == changed_index:
                        return mid_left
                    mid_left -= 1
    return -1


def binary_insert(index_list, changed_index, H):

    changed_value = H[changed_index]
    low = 0
    high = len(index_list) - 1

    if high == -1: # empty list
        index_list.append(changed_index)
        return
    
    # check side case
    if changed_value >= H[index_list[0]]:
        index_list.insert(0, changed_index)
        return
    if changed_value <= H[index_list[len(index_list) - 1]]:
        index_list.insert(len(index_list), changed_index)
        return 
    
    while high >= low + 2:
        mid = (high + low)//2
        if H[index_list[mid]] == changed_value:
            index_list.insert(mid, changed_index)
            return
        if H[index_list[mid]] < changed_value:
            high = mid
        else:
            low = mid

    #  low <= high <= low + 1
    index_list.insert(high, changed_index)


# not finished yet
def incremental_sort(index_list, changed_index_list, H_old, H_new):   # changed_index_list and prev_values are 1-1 corresponse
    # delete the changed elements
    positions = []
    for index in changed_index_list:
        pos = binary_find(index_list, index, H_old)
        if pos != -1:
            positions.append(pos)
    for index_del in sorted(positions, reverse=True):
        del index_list[index_del]

    # re-insert the changed elements
    for index in changed_index_list:
        if H_new[index] != 0:
            binary_insert(index_list, index, H_new)

    


def construct_naive(KG, K, topic_eids):
    P = Summary(KG)
    topic_mids = []
    # turn eid into mid
    for topic_eid in topic_eids:
        topic_mids.append(KG.id_entity_[topic_eid])
    i = 0
    while P.number_of_triples() < K:
        P.add_entity(topic_mids[i])
        i += 1
        if i == len(topic_eids):
            while P.number_of_triples() < K:
                P.add_random_triple()
            break
    return P

    
def construct_complete(KG, K, index_list):
    P = Summary(KG)
    need_random = 1

    for i in range(len(index_list)):
        triple_to_add = (KG.id_entity(index_list[i][0]), KG.id_relation(index_list[i][1]), KG.id_entity(index_list[i][2]))
        P.add_triple(triple_to_add)
        if P.number_of_triples() >= K:
            need_random = 0
            break

    if need_random:
        need = K - P.number_of_triples()
        triple_to_add = random.sample(list(KG.triples()), k = need)
        for triple in triple_to_add:
            P.add_triple(triple)
    return P

"""
@param KG: 知识图谱
@param K: 目标数量
@param query_log: 相当于所有的查询请求
@param gamma: 时间衰减系数
@param diameter:
@param alpha:
@param query_num_per_test:
"""
def APEX_N(KG, K, query_log, query_num_per_test=1, gamma=GAMMA, diameter = 1, alpha=0.3):
    print('Running APEX-N')
    # 每次更新摘要图所花费的时间
    update_time_list = []
    # 每次测试得到的平均 F1 分数
    acc_list = []
    # 时间为0
    t = 0
    # 查询请求的总量
    num_queries_total = len(query_log)
    # 存储不同扩散步数对应的稀疏热传播矩阵
    csr_indirect_matrices = {}
    # 生成n*n的单位矩阵：n是图谱的实体数。然后这个list我个人感觉可以理解为一个三维的坐标系，每层一个矩阵。
    csr_indirect_matrices[0] = sp.eye(KG.number_of_entities())
    """
    单位矩阵如下
    1 0 0 0 0
    0 1 0 0 0
    0 0 1 0 0
    0 0 0 1 0
    0 0 0 0 1
    """
    print('calculating heat matrices (one-time computing)')
    # 一个随机的扩散层数。
    for i in range(diameter):
        # 最多有diameter层
        """
        就用这个函数里的例子 csr_matrix_indirect_heat()
        KG.csr_matrix_indirect_heat()如下
        0   1/2   0     0     0
        1   0     1/3   0     0
        0   1/2   0     2/3   0
        0   0     2/3   0     1
        0   0     0     1/3   0
        csr_indirect_matrices[]
        """
        csr_indirect_matrices[i+1] = alpha * KG.csr_matrix_indirect_heat() * csr_indirect_matrices[i]
    # initialize heat
        """
        人工走一下这个遍历过程吧，假设就三层，alpha 是 0.3不好算，用 0.5吧
        第一层
        1 0 0 0 0        0   1/2   0     0     0                                 0   1/4  0    0  0                                           1/2   0     1/6    0     0
        0 1 0 0 0        1   0     1/3   0     0                                 1/2  0   1/6  0  0                                           0     2/3   0      2/9   0
        0 0 1 0 0   ->   0   1/2   0     2/3   0 与第一层相乘还要乘 alpha得到第二层   0   1/4  0    0  0 -> 这个再与 alpha 和那个矩阵相乘得到第三层     1/2   0     11/18  0     2/3  
        0 0 0 1 0        0   0     2/3   0     1                                 0    0   2/6  0  1/2                                         0     1/3   0      4/9   0
        0 0 0 0 1        0   0     0     1/3   0                                 0   0    0    1/6 0                                          0     0     2/9    0     1/3  
        再理一下这个 csr 的数组,简称他 csr，那个图谱的简称 M 吧
        csr0 = I
        csr1 = a M
        csr2 = a^2 M^2
        csr3 = a^3 M^3。。。以此类推下去有递推公式：csr[k] = a^k M^k   就是矩阵的乘方然后乘了个系数
        
        现在理解一下这个矩阵中每一层的含义
        A^k 的第 j 列 = 从第 j 个点出发，走 k 步能到各个点的“所有路径的累计结果”
        怎么理解这个过程：从我来看，我还是看最初的A 实体那一列到 B 的概率是1，到其他的都是 0
        然后乘方之后还是以 A 为例。他的计算过程理解为A 走一步到实体 B 的概率 × 实体B再走一步到其他实体的概率。含义其实就是从列代表的实体为起点，走 K 步到行代表的实体为终点的概率
        """
    print('heat matrices calculated')
    """
    综上所述，csr 这个数组第 K 层的含义就是从列代表的实体为起点，走 K 步到行代表的实体为终点的概率
    """

    """
    这里创建一个内部全部为 0 的向量
    """
    initial_heat = np.zeros(KG.number_of_entities())
    index_list = []
    # 这里是查询参数
    first_q = query_log[0]
    # 这里把之前的向量，图谱，层数，概率都穿进去，（这个函数写了注释，建议看看）
    # heat 为影响力矩阵（这个需要从函数里面理解这个词的意思）。_为受影响较大的实体
    heat, _ = Heat_Diffuse(initial_heat, KG, first_q, diameter, csr_indirect_matrices)
    # 从大到小排序
    sorted_heat = np.sort(heat)[::-1]
    # 从大到小排序后，当前元素在原 list 中的位置
    """
    举例说明一下：【3，5，2，6】
    排序：【2，3，5，6】
    args：【2，0，1，3】
    """
    sorted_args = np.argsort(heat)[::-1]
    i = 0
    while sorted_heat[i] > 0:
        # 把 args 添加到 index_list里面，我觉得不需要纠结这个 while 循环的操作在干什么
        index_list.append(sorted_args[i])
        i += 1
    P = construct_naive(KG, K, topic_eids = index_list)
    # test for initial graph
    if DETAILED_LOGGING:
        logging.info('Initial Test')
    total_F1, total_precision, total_recall = total_query_log_metrics(P, query_log[1: 1+query_num_per_test])
    if DETAILED_LOGGING:
        logging.info('\t  Total F1/precision/recall')
        logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
            total_F1, total_precision, total_recall))
    
    avg_F1, avg_precision, avg_recall = average_query_log_metrics(P, query_log[1: 1+query_num_per_test])
    if DETAILED_LOGGING:
        logging.info('\t  Average F1/precision/recall')
        logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
            avg_F1, avg_precision, avg_recall))

    # update phase
    # while t < num_queries_total - query_num_per_test:
    print('Adaptive personalized knowledge graph summarization for {} timestamps'.format(num_queries_total - query_num_per_test - 1))
    for t in tqdm(range(1, num_queries_total - query_num_per_test)):
        t0 = time()
        heat = heat * gamma
        heat_new, changed_index_list = Heat_Diffuse(heat, KG, query_log[t], diameter, csr_indirect_matrices)
        for i in range(len(heat_new)):
            if heat_new[i] > 0 and heat_new[i] < 1e-4:
                heat_new[i] = 0

        incremental_sort(index_list, changed_index_list, heat, heat_new)
        # print('incremental end')
        new_index_list = []
        for i in range(len(index_list)):
            if heat_new[index_list[i]] != 0:
                new_index_list.append(index_list[i])
            else:
                break
        index_list = new_index_list
        heat = heat_new
        P = construct_naive(KG, K, topic_eids= index_list)
        update_time = time() - t0
        update_time_list.append(update_time)

        if DETAILED_LOGGING:
            logging.info('\t  Adapting for time: {}'.format(t))
            logging.info('\t  Time: {:.2f} seconds'.format(update_time))

        # Evaluate question answering on the testing queries
        total_F1, total_precision, total_recall = total_query_log_metrics(P, query_log[t+1: t+1+query_num_per_test])
        if DETAILED_LOGGING:
            logging.info('\t  Total F1/precision/recall')
            logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
                total_F1, total_precision, total_recall))
        
        avg_F1, avg_precision, avg_recall = average_query_log_metrics(P, query_log[t+1: t+1+query_num_per_test])
        if DETAILED_LOGGING:
            logging.info('\t  Average F1/precision/recall')
            logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
                avg_F1, avg_precision, avg_recall))
        
        acc_list.append(avg_F1)
        t += 1     
    # 计算平均值
    logging.info('\t  Ave Time on Each Training Log: {:.2f} seconds'.format(np.mean(update_time_list)))
    logging.info('\t  Ave Ave F1 on Each Training Log: {:.2f}'.format(np.mean(acc_list)))
    # 返回评分数组和更新时间数组
    return acc_list, update_time_list



def APEX(KG, K, query_log, query_num_per_test=1, gamma=GAMMA, diameter = 1, alpha=0.3):
    print('Running APEX')
    smoothing = 0.5
    update_time_list = []
    acc_list = []
    t = 0
    num_queries_total = len(query_log)
    csr_indirect_matrices = {}
    csr_indirect_matrices[0] = sp.eye(KG.number_of_entities())
    print('calculating heat matrices (one-time computing)')
    for i in range(diameter):
        csr_indirect_matrices[i+1] = alpha * KG.csr_matrix_indirect_heat() * csr_indirect_matrices[i]

    print('heat matrices calculated')
    # initial state
    index_list = []
    q = np.zeros(KG.number_of_entities())
    e = np.zeros(KG.number_of_entities())
    r = np.zeros(KG.number_of_relationships())

    # q (query), e (entity heat) and r after first query
    first_q = query_log[0]
    parse = first_q['Parse']
    topic_mid = parse['TopicEntityMid']
    topic_eid = KG.entity_id(parse['TopicEntityMid'])
    relation = parse['InferentialChain'][0]
    answers = KG[topic_mid][relation]
    q[topic_eid] += 1
    answers_rid = np.zeros(len(answers), dtype = int)
    for i, item in enumerate(answers):
        answers_rid[i] = KG.entity_id(item)
        q[answers_rid[i]] += 1/len(answers)

    for i in range(diameter):
        e += csr_indirect_matrices[i] * q
    
    r[KG.relation_id(relation)] = 1    

    # the Heat
    H = {}
    for triple in KG.triples():
        e1, re, e2 = triple
        e1 = KG.entity_id(e1)
        re = KG.relation_id(re)
        e2 = KG.entity_id(e2)
        if e[e1] != 0 and r[re] != 0 and e[e2] != 0:
            H[(e1, re, e2)] = e[e1] * (r[re] + smoothing) * e[e2]
            index_list.append((e1, re, e2))
        
    # sort index_list
    h_for_sort = []
    for index in index_list:
        h_for_sort.append(H[index])

    h_for_sort = np.array(h_for_sort)

    sorted_args = np.argsort(h_for_sort)[::-1]
    sorted_index_list = []
    for i in range(len(sorted_args)):
        sorted_index_list.append(index_list[sorted_args[i]])
    index_list = sorted_index_list

    # construct initial summary
    P = construct_complete(KG, K, index_list)
    # test for initial graph
    if DETAILED_LOGGING:
        logging.info('Initial Test')
    total_F1, total_precision, total_recall = total_query_log_metrics(P, query_log[1: 1+query_num_per_test])
    if DETAILED_LOGGING:
        logging.info('\t  Total F1/precision/recall')
        logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
            total_F1, total_precision, total_recall))
    
    avg_F1, avg_precision, avg_recall = average_query_log_metrics(P, query_log[1: 1+query_num_per_test])
    if DETAILED_LOGGING:
        logging.info('\t  Average F1/precision/recall')
        logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
            avg_F1, avg_precision, avg_recall))
        

    # update phase
    t += 1
    # while t < num_queries_total - query_num_per_test:
    print('Adaptive personalized knowledge graph summarization for {} timestamps'.format(num_queries_total - query_num_per_test - 1))
    for t in tqdm(range(1, num_queries_total - query_num_per_test)):
        t0 = time()
        H_new = {}
        for key in H:
            H_new[key] = H[key]*gamma**3
        # incremental update
        q_T = np.zeros(KG.number_of_entities())
        parse = query_log[t]['Parse']
        topic_mid = parse['TopicEntityMid']
        topic_eid = KG.entity_id(parse['TopicEntityMid'])
        relation = parse['InferentialChain'][0]
        answers = KG[topic_mid][relation]
        q_T[topic_eid] += 1
        answers_rid = np.zeros(len(answers), dtype = int)
        for i, item in enumerate(answers):
            answers_rid[i] = KG.entity_id(item)
            q_T[answers_rid[i]] += 1/len(answers)

        q = q*gamma + q_T
        e_new, changed_entity_list = Heat_Diffuse(e, KG, query_log[t], diameter, csr_indirect_matrices)
        r = r*gamma
        r[KG.relation_id(relation)] += 1

        for i in H_new:
            if H_new[i] > 0 and H_new[i] < 1e-5:
                H_new[i] = 0
        
        changed_triples_in_id = set()


        for changed_entity_id in changed_entity_list:
            potential_triples_vector = KG.csr_matrix_indirect()[changed_entity_id, :]
            rows, cols = potential_triples_vector.nonzero()
            for another_entity_id in cols:
                if e[another_entity_id] == 0 and e_new[another_entity_id] == 0:
                    continue
                triple_found = KG.find_triple_by_entities_indirect(changed_entity_id, another_entity_id)
                if triple_found is not None:
                    # for triple_ in triple_found:
                    if triple_found[1] < KG.number_of_relationships():
                        if triple_found[1] != relation and r[triple_found[1]] == 0:
                            continue
                        changed_triples_in_id.add(triple_found)

        e = e_new

        for triple in KG.triples_by_relation_id(KG.relation_id(relation)):
            changed_triples_in_id.add(triple)

        changed_triples_in_id_list = list(changed_triples_in_id)
        for triple_in_id in changed_triples_in_id_list:
            new_value = e[triple_in_id[0]] * ((r[triple_in_id[1]]) + smoothing) * e[triple_in_id[2]]
            if new_value > 0:
                H_new[triple_in_id] = new_value
            else:
                changed_triples_in_id.remove(triple_in_id)


        for triple_in_id in list(changed_triples_in_id):
            if triple_in_id not in H:
                H[triple_in_id] = 0


        # incremental sort
        incremental_sort(index_list, changed_triples_in_id, H, H_new)

        new_index_list = []
        for i in range(len(index_list)):
            if H_new[index_list[i]] != 0:
                new_index_list.append(index_list[i])
            else:
                break
        index_list = new_index_list

        H = H_new

        P = construct_complete(KG, K, index_list)
        update_time = time() - t0
        update_time_list.append(update_time)

        if DETAILED_LOGGING:
            logging.info('\t  Adapting for time: {}'.format(t))
            logging.info('\t  Time: {:.2f} seconds'.format(update_time))

        # Evaluate question answering on the testing queries
        total_F1, total_precision, total_recall = total_query_log_metrics(P, query_log[t+1: t+1+query_num_per_test])
        if DETAILED_LOGGING:
            logging.info('\t  Total F1/precision/recall')
            logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
                total_F1, total_precision, total_recall))
        
        avg_F1, avg_precision, avg_recall = average_query_log_metrics(P, query_log[t+1: t+1+query_num_per_test])
        if DETAILED_LOGGING:
            logging.info('\t  Average F1/precision/recall')
            logging.info('\t    {:.2f}/{:.2f}/{:.2f}'.format(
                avg_F1, avg_precision, avg_recall))

        acc_list.append(avg_F1)
        t += 1

    logging.info('\t  Ave Time on Each Training Log: {:.2f} seconds'.format(np.mean(update_time_list)))
    logging.info('\t  Ave Ave F1 on Each Training Log: {:.2f}'.format(np.mean(acc_list)))

    return acc_list, update_time_list



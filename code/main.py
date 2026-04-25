import argparse
import random
import logging
import json
import pdb
import numpy as np
from src.base import YAGO, DBPedia, Freebase, MetaQA
from src.user import query_log_by_mids, query_log_by_topics
from src.apex import APEX, APEX_N

logging.basicConfig(format='[%(asctime)s] - %(message)s',
                    level=logging.DEBUG,
                    filename='log.log', filemode='a')

class SummaryMethod(object):
    """用于封装摘要函数及其相关元信息"""

    def __init__(self, fn, name, **kwargs):
        """
        :param fn: 要调用的摘要函数
        :param name: 方法名称（用于展示）
        :param kwargs: 传递给函数的额外参数
        """
        self.fn_ = fn
        self.name_ = name
        self.kwargs_ = kwargs

    def name(self):
        return self.name_

    def kwargs(self):
        return self.kwargs_

    def __call__(self, KG, K, query_log):
        """
        :param KG: 知识图谱
        :param K: 摘要约束（大小限制）
        :param query_log: 查询日志
        :return: 方法执行结果
        """
        return self.fn_(KG, K, query_log, **self.kwargs_)


# 知识图谱映射（可选数据集）
KG_MAPPING = {
    'YAGO': YAGO(rdf_gz='yagoFacts.gz', query_dir='final/', mid_dir='by-mid/'),
    'Freebase': Freebase(query_dir='queries/final/'),
    'DBpedia': DBPedia(),
    'MetaQA': MetaQA(),
}

# 摘要算法
METHODS = {
    'apex': SummaryMethod(APEX, 'APEX'),
    'apex-n': SummaryMethod(APEX_N, 'APEX-N'),
}


def answer_queries_in_log(KG, K, query_log, summary_methods,
                          acc_list_apex_n, acc_list_apex,
                          update_time_apex_n, update_time_apex,
                          query_num_per_test=1, gamma=0.5):
    """
    执行查询并评估摘要方法

    :param KG: 知识图谱
    :param K: 摘要大小限制
    :param query_log: 查询日志
    :param summary_methods: 使用的方法列表
    """

    for summary_method in summary_methods:
        logging.info('\t---使用 {} 进行摘要---'.format(summary_method.name()))

        if summary_method.name_ == 'APEX-N':
            acc_list, update_time_list = APEX_N(KG, K, query_log, query_num_per_test, gamma=gamma)
            acc_list_apex_n += acc_list
            update_time_apex_n += update_time_list
        if summary_method.name_ == 'APEX':
            acc_list, update_time_list = APEX(KG, K, query_log, query_num_per_test, gamma=gamma)
            acc_list_apex += acc_list
            update_time_apex += update_time_list


def float_in_zero_one(value):
    """检查浮点数是否在 [0,1] 范围内"""
    value = float(value)
    if value < 0 or value > 1:
        raise argparse.ArgumentTypeError('数值必须在 0 到 1 之间')
    return value


def positive_int(value):
    """检查是否为正整数"""
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError('数值必须为正整数')
    return value

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--kg', choices=list(KG_MAPPING.keys()), default='MetaQA',
            help='选择要使用的知识图谱')

    parser.add_argument('--n-queries', type=positive_int, default=200,
            help='每个用户模拟的查询数量（默认 200）')

    parser.add_argument('--n-topic-mids', type=positive_int, default=20,
            help='每个用户关注的主题实体数量（默认 20）')

    parser.add_argument('--n-topics', type=positive_int, default=10,
            help='每个用户日志中的主题数量（仅 Freebase 使用）')

    parser.add_argument('--n_users', type=positive_int, default=2,
            help='模拟用户数量（默认 2）')

    parser.add_argument('--start_user', type=positive_int, default=0,
            help='起始用户编号（默认 0）')

    parser.add_argument('--percent-triples', type=float_in_zero_one, default=0.0001,
            help='用于摘要的三元组比例（K 的比例）')

    parser.add_argument('--random-query-prob', type=float_in_zero_one, default=0,
            help='随机查询的概率（而非主题查询）')

    parser.add_argument('--shuffle', action='store_true',
            help='是否打乱查询日志')

    parser.add_argument('--method', nargs='+', default=['apex'],
            choices=list(METHODS.keys()),
            help='选择摘要方法')
    parser.add_argument('--save-queries', action='store_true',
            help='是否保存生成的查询（会覆盖原文件）')

    parser.add_argument('--load-queries', action='store_true',
            help='是否从数据集加载查询（默认不加载）')

    parser.add_argument('--query-num-per-test', type=positive_int, default=1,
            help='每次测试使用的查询数量')

    parser.add_argument('--gamma', type=float_in_zero_one, default=0.5,
            help='APEX / APEX-N 的衰减因子')
    return parser.parse_args()

def main():
    acc_list_apex_n = []
    acc_list_apex = []
    update_time_apex_n = []
    update_time_apex = []
    args = parse_args()
    if (args.save_queries is True) and (args.load_queries is True):
        raise NotImplementedError

    if (args.save_queries is True):
        print('警告：将覆盖已有文件，是否继续？')
        pdb.set_trace()

    # 获取知识图谱
    KG = KG_MAPPING[args.kg]
    # 从输入参数中提取摘要方法
    summary_methods = [METHODS[name] for name in args.method]
    logging.info('正在加载 {}'.format(KG.name()))
    # 加载知识图谱
    KG.load()
    logging.info('加载完成 {}'.format(KG.name()))

    # 计算摘要大小 K： 三元组数量乘以百分比然后取整
    K = int(args.percent_triples * KG.number_of_triples())
    logging.info('K = {}'.format(K))

    # 模拟用户（默认是0到2的随机数）
    for user in range(args.start_user, args.start_user + args.n_users):
        logging.info('---模拟用户 {}---'.format(user))
        # 更新图的用户
        KG.update_user(user)
        logging.basicConfig(filename=KG.user_dir + '/log.log')
        # 根据数据集选择
        if args.kg == 'Freebase':
            topics = random.sample(KG.topics(), k=args.n_topics)

            query_log = query_log_by_topics(
                KG, topics, args.n_mids_per_topic, args.n_queries,
                shuffle=args.shuffle,
                random_query_prob=args.random_query_prob)

        elif args.kg == 'MetaQA':
            args.save_queries = False
            args.load_queries = True
            query_log = []
            # 查询数量里取随机数
            for i in range(args.n_queries):
                # 从final目录里面找到q对应的json并且添加日志
                with open(KG.query_dir() + "q" + str(i) + ".json", "r") as f:
                    # 添加查询日志（可以不看）
                    query_log.append(json.load(f))

            logging.info('---已加载 {} 条查询日志---'.format(len(query_log)))

        else:
            topic_mids = random.sample(list(KG.triples_.keys()), k=args.n_topic_mids)

            if args.load_queries:
                query_log = []
                for i in range(args.n_queries):
                    with open(KG.query_dir() + "q" + str(i) + ".json", "r") as f:
                        query_log.append(json.load(f))

                logging.info('---已加载 {} 条查询日志---'.format(len(query_log)))

            else:
                query_log = query_log_by_mids(
                    KG, topic_mids, args.n_queries,
                    topic_dist=np.ones(len(topic_mids)) / len(topic_mids),
                    shuffle=args.shuffle,
                    random_query_prob=args.random_query_prob,
                    whether_save=args.save_queries)

                logging.info('---生成了 {} 条查询日志---'.format(len(query_log)))
        # 保存查询的话就把日志输出出来
        if args.save_queries:
            logging.info('---正在保存查询---')
            for i in range(len(query_log)):
                with open(KG.query_dir() + "q" + str(i) + ".json", "w") as outfile:
                    json.dump(query_log[i], outfile)

        answer_queries_in_log(
            KG, K, query_log, summary_methods,
            acc_list_apex_n, acc_list_apex,
            update_time_apex_n, update_time_apex,
            query_num_per_test=args.query_num_per_test,
            gamma=args.gamma)

    # 输出结果
    if len(acc_list_apex) > 0:
        print('APEX 平均 F1 分数:', np.mean(acc_list_apex))

    if len(update_time_apex) > 0:
        print('APEX 平均更新时间（秒）:', np.mean(update_time_apex))

    if len(acc_list_apex_n) > 0:
        print('APEX-N 平均 F1 分数:', np.mean(acc_list_apex_n))

    if len(update_time_apex_n) > 0:
        print('APEX-N 平均更新时间（秒）:', np.mean(update_time_apex_n))

    logging.info('程序运行结束，详细信息请查看日志文件')


if __name__ == '__main__':
    main()
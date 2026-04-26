主要目的是学一下这个项目怎么用才建的这个仓库
```sh
cd code

# quick start with pre-generated query on MetaQA
python main.py --kg MetaQA --method apex apex-n --percent-triples 0.0001 --n_users 1

# generate user queries and test on DBpedia and YAGO
python main.py --kg DBpedia --method apex apex-n --save-queries --percent-triples 0.000001 --n_users 1

python main.py --kg YAGO --method apex apex-n --save-queries --percent-triples 0.000001 --n_users 1
```
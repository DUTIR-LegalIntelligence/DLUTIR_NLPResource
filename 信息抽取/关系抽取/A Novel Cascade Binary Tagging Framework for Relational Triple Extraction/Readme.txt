A Novel Cascade Binary Tagging Framework for Relational Triple Extraction

本文提出了一种两段式的联合学习策略提取实体关系三元组，先进行头实体识别，而后识别关系特定的尾实体。具体来说，论文提出了一种新的框架（CASREL），该框架从基础公式中导出。新框架不再像以前的工作那样将关系视为离散的标签，而是将关系建模为将头实体映射到尾实体的函数，这样可以自然地处理重叠问题。实验表明，即使在其编码器模块使用随机初始化的BERT编码器时，CASREL框架的性能已经超过了最先进的方法。当使用预训练的BERT编码器时，它的性能得到了进一步的提升，在两个公共数据集NYT和WebNLG上取得了最好的效果。
github : https://github.com/weizhepei/CasRel

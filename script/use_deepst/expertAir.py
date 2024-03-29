# -*- coding: utf-8 -*-
"""
Usage:
    THEANO_FLAGS="device=gpu0" python exptBikeNYC.py
"""
from __future__ import print_function
import os
import pickle
import numpy as np
import math

from keras.optimizers import Adam
from keras.callbacks import EarlyStopping, ModelCheckpoint
from deepst.models.STResNet import stresnet
from deepst.config import Config
import deepst.metrics as metrics
from deepst.datasets import BikeNYC
np.random.seed(1337)  # for reproducibility

# parameters
# data path, you may set your own data path with the global envirmental
# variable DATAPATH
DATAPATH = Config().DATAPATH  #配置的环境
nb_epoch = 1  # number of epoch at training stage  训练时的迭代次数
nb_epoch_cont = 1  # number of epoch at training (cont) stage    阶段性的
batch_size = 32  # batch size   每次训练的批次
T = 24  # number of time intervals in one day   一天的周期迭代次数

lr = 0.0002  # learning rate
len_closeness = 6  # length of closeness dependent sequence   考虑的相邻的迭代次数
len_period = 4  # length of peroid dependent sequence       以相邻周期四个作为预测趋势
len_trend = 4  # length of trend dependent sequence    以前面4个作为趋势性
nb_residual_unit = 4   # number of residual units   残差单元数量

nb_flow = 1  # there are two types of flows: new-flow and end-flow
# divide data into two subsets: Train & Test, of which the test set is the
# last 10 days    使用10天数据进行测试
days_test = 10
len_test = T * days_test   #测试用的时间戳数量
map_height, map_width = 35, 11   # grid size   每个代表流量意义的格点图的大小为16*8
# For NYC Bike data, there are 81 available grid-based areas, each of
# which includes at least ONE bike station. Therefore, we modify the final
# RMSE by multiplying the following factor (i.e., factor).
nb_area = 81  # 共有81个基于网格点的区域， 每个区域至少有1个自行车站
# m_factor 计算得到影响因素   影响因子的具体计算为什么这样算
path_result = 'RET'
path_model = 'MODEL'

if os.path.isdir(path_result) is False:
    os.mkdir(path_result)
if os.path.isdir(path_model) is False:
    os.mkdir(path_model)


def build_model(external_dim):
    #创建模型时   首先指定进行组合时的参数    将配置分别放进不同的区域中（就是相近性的长度 ，周期性的长度等）
    c_conf = (len_closeness, nb_flow, map_height,
              map_width) if len_closeness > 0 else None
    p_conf = (len_period, nb_flow, map_height,
              map_width) if len_period > 0 else None
    '''
    趋势性的数据暂时不要
    t_conf = (len_trend, nb_flow, map_height,
              map_width) if len_trend > 0 else None
    '''
    #根据不同的配置定义残差神经网络模型  这个stresnet是定义好的，传入关于不同方面的配置，最后会返回根据参数组合好的模型
    model = stresnet(c_conf=c_conf, p_conf=p_conf,
                     external_dim=external_dim, nb_residual_unit=nb_residual_unit)
    adam = Adam(lr=lr) #接下来 定义学习率和损失函数值
    model.compile(loss='mse', optimizer=adam, metrics=[metrics.rmse])
    model.summary()
    # from keras.utils.visualize_util import plot
    # plot(model, to_file='model.png', show_shapes=True)
    return model


def main():
    # load data
    print("loading data...")
    #开始加载数据   加载时指定各种参数，会根据传入的参数进行加载数据的分离。
    X_train, Y_train, X_test, Y_test, external_dim, timestamp_train, timestamp_test = BikeNYC.load_data(
        T=T, nb_flow=nb_flow, len_closeness=len_closeness, len_period=len_period, len_test=len_test,
        preprocess_name='preprocessing.pkl', meta_data=True)

    print("\n days (test): ", [v[:8] for v in timestamp_test[0::T]])

    print('=' * 10)
    print("compiling model...")
    print(
        "**at the first time, it takes a few minites to compile if you use [Theano] as the backend**")
    model = build_model(external_dim)
    hyperparams_name = 'c{}.p{}.t{}.resunit{}.lr{}'.format(
        len_closeness, len_period, len_trend, nb_residual_unit, lr)
    fname_param = os.path.join('MODEL', '{}.bes'
                                        ''
                                        't.h5'.format(hyperparams_name))

    early_stopping = EarlyStopping(monitor='val_rmse', patience=5, mode='min')
    model_checkpoint = ModelCheckpoint(
        fname_param, monitor='val_rmse', verbose=0, save_best_only=True, mode='min')

    print('=' * 10)
    print("training model...")
    history = model.fit(X_train, Y_train,
                         nb_epoch=nb_epoch,
                         batch_size=batch_size,
                         validation_split=0.1,
                         callbacks=[early_stopping, model_checkpoint],
                         verbose=1)
    model.save_weights(os.path.join(
         'MODEL', '{}.h5'.format(hyperparams_name)), overwrite=True)
    pickle.dump((history.history), open(os.path.join(
        path_result, '{}.history.pkl'.format(hyperparams_name)), 'wb'))

    print('=' * 10)
    print('evaluating using the model that has the best loss on the valid set')

    model.load_weights(fname_param)
    score = model.evaluate(X_train, Y_train, batch_size=Y_train.shape[
                           0] // 24, verbose=0)
    print('Train score: %.6f rmse (norm): %.6f rmse (real): ' %
          (score[0], score[1]))

    score = model.evaluate(
        X_test, Y_test, batch_size=Y_test.shape[0], verbose=0)
    print('Test score: %.6f rmse (norm): %.6f rmse (real):' %
          (score[0], score[1]))

    print('=' * 10)
    print("training model (cont)...")
    fname_param = os.path.join(
        'MODEL', '{}.cont.best.h5'.format(hyperparams_name))
    model_checkpoint = ModelCheckpoint(
        fname_param, monitor='rmse', verbose=0, save_best_only=True, mode='min')
    history = model.fit(X_train, Y_train, nb_epoch=nb_epoch_cont, verbose=1, batch_size=batch_size, callbacks=[
                        model_checkpoint], validation_data=(X_test, Y_test))
    pickle.dump((history.history), open(os.path.join(
        path_result, '{}.cont.history.pkl'.format(hyperparams_name)), 'wb'))
    model.save_weights(os.path.join(
        'MODEL', '{}_cont.h5'.format(hyperparams_name)), overwrite=True)

    print('=' * 10)
    print('evaluating using the final model')
    score = model.evaluate(X_train, Y_train, batch_size=Y_train.shape[
                           0] // 24, verbose=0)
    print('Train score: %.6f rmse (norm): %.6f rmse (real):' %
          (score[0], score[1]))

    score = model.evaluate(
        X_test, Y_test, batch_size=Y_test.shape[0], verbose=0)
    print('Test score: %.6f rmse (norm): %.6f rmse (real): ' %
          (score[0], score[1]))

if __name__ == '__main__':
    main()

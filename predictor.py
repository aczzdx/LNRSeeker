
from alpha import feature_extractor
import argparse

# %load save_model.py
from __future__ import print_function

import multiprocessing
import pickle as pkl

import numpy as np
import pandas as pd

import sklearn.model_selection
import time
import logging

import keras.objectives
import keras.optimizers
import sklearn.metrics
from keras.layers import Dense, Input
from keras.models import Model

from alpha import feature_extractor
from alpha.transform import Transform
from hexmer import get_score_matrix
import json

import logging

class predictor:

    # 之所以将predictor写成类，主要是为了方便存储和复现
    # 之前得到的网络

    def __init__(self):
        self.model = None
        self.atrans = None # atrans 是将数据归一化的结构
        self.s_score_matrix = None # s_score_matrix 是计算SScore的矩阵
        self.fe = None
        self._logger = None

    @property
    def logger(self):
        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    def train(self, coding_filename, non_coding_filename,
              sScoreMatrix_filename, save_input=False):

        # 读取数据

        sScoreMatrix = get_score_matrix(coding_filename, non_coding_filename)
        self.fe = fe = feature_extractor(sScoreMatrix)

        fss = list()

        with open(coding_filename, "r") as f:
            lines = f.readlines()
        for i in range(0, len(lines), 2):
            if i + 1 >= len(lines):
                break
            new_dict = fe.extract_features_using_dict(lines[i][:-1], lines[i + 1][:-1])
            if 'exception' in new_dict.keys():
                print("error")
            else:
                new_dict['verdict'] = 0
                fss.append(new_dict)

        with open(non_coding_filename, "r") as f:
            lines = f.readlines()
        for i in range(0, len(lines), 2):
            if i + 1 >= len(lines):
                break
            new_dict = fe.extract_features_using_dict(lines[i][:-1], lines[i + 1][:-1])
            if 'exception' in new_dict.keys():
                print("error")
            else:
                new_dict['verdict'] = 1
                fss.append(new_dict)

        df = pd.DataFrame(fss)
        df = df.drop(['ID', 'seq', 'kozak1', 'kozak2'], axis=1)

        if save_input:
            import random
            temp_int = random.randint(1, 65536)
            df.to_csv("data_" + str(temp_int) + ".csv", index_col=False)

        y = df.verdict[:]
        X = df.drop('verdict', axis=1)

        # 归一化
        self.atrans = Transform.transform(X)
        X_train = self.atrans.transform(X)
        y_train = y

        # 载入神经网络的最佳参数
        params = {'mlp_epochs': 50, 'mlp': 0, 'hidden_dim_3': 125, 'alpha': 1, 'hidden_dim_1': 100, 'a_epoch': 40, 'hidden_dim_2': 100}

        #    logger.info("Checking the model: \n" + str(params))
        #else:
        #    logger.info("Checking the default model.")

        verbose_level = 2
        myorg_dim = len(X_train[0])
        original_dim = (len(X_train[0]),)
        latent_dim = original_dim

        if 'hidden_dim_1' in params.keys():
            hidden_dim_1 = params['hidden_dim_1']
        else:
            hidden_dim_1 = 200

        # hidden_dim_1 = {{choice([200, 300, 400, 500])}}

        if 'hidden_dim_2' in params.keys():
            hidden_dim_2 = params['hidden_dim_2']
        else:
            hidden_dim_2 = 200

        if 'hidden_dim_3' in params.keys():
            hidden_dim_3 = params['hidden_dim_3']
        else:
            hidden_dim_3 = 50

        if 'mlp' in params.keys():
            is_mlp = params['mlp']
        else:
            is_mlp = False

        if 'a_epoch' in params.keys():
            a_epoach = params['a_epoch']
        else:
            a_epoach = 15

        if 'mlp_epoch' in params.keys():
            mlp_epoch = params['mlp_epoch']
        else:
            mlp_epoch = 50

        if 'is_relu' in params.keys():
            is_relu = params['is_relu']
        else:
            is_relu = False

        if 'alpha'in params.keys():
            alpha = params['alpha']
        else:
            alpha = 1

        hidden_dim_4 = 10
        nb_epoch = 5

        # 定义网络
        x = Input(shape=original_dim)
        encoder_1 = Dense(hidden_dim_1, activation='sigmoid')
        decoder_1 = Dense(original_dim[0], activation='sigmoid')
        h = encoder_1(x)
        x_hat = decoder_1(h)

        # Autoencoder的损失函数
        def ae_loss(y_true, y_pred):
            original_loss = keras.objectives.mean_squared_error(y_true, y_pred)
            kld_loss = keras.objectives.kld(y_true, y_pred)
            return original_loss + alpha * kld_loss

        auto_encdoer = Model(x, x_hat)
        auto_encdoer.compile(optimizer="RMSprop", loss=ae_loss)
        auto_encdoer.fit(X_train, X_train, epochs=a_epoach, shuffle=True, verbose=verbose_level)

        encoder = Model(x, h)
        h1 = encoder.predict(X_train)
        x2 = Input(shape=(hidden_dim_1,))
        encoder_2 = Dense(hidden_dim_2, activation='sigmoid')
        decoder_2 = Dense(hidden_dim_1, activation='sigmoid')
        hh = encoder_2(x2)
        h_hat = decoder_2(hh)
        auto_encdoer_2 = Model(x2, h_hat)
        auto_encdoer_2.compile(optimizer="RMSprop", loss=ae_loss)
        auto_encdoer_2.fit(h1, h1, epochs=a_epoach, shuffle=True, verbose=verbose_level)
        encoder2 = Model(x2, hh)
        h2 = encoder2.predict(h1)
        x3 = Input(shape=(hidden_dim_2,))
        encoder_3 = Dense(hidden_dim_3, activation='sigmoid')
        decoder_3 = Dense(hidden_dim_2, activation='sigmoid')

        hh3 = encoder_3(x3)
        h_hat = decoder_3(hh3)
        auto_encdoer_3 = Model(x3, h_hat)
        auto_encdoer_3.compile(optimizer="RMSprop", loss=ae_loss)
        auto_encdoer_3.fit(h2, h2, epochs=a_epoach, shuffle=True, verbose=verbose_level)
        hhh = encoder_2(h)
        hhh = encoder_3(hhh)

        if is_relu:
            active_name = 'relu'
        else:
            active_name = 'sigmoid'

        if not is_mlp == 0:
            y = Dense(is_mlp, activation=active_name)(hhh)
            y = Dense(1, activation='sigmoid')(y)
        else:
            y = Dense(1, activation='sigmoid')(hhh)

        self.model = Model(x, y)
        self.model.compile(optimizer="RMSprop", loss=keras.objectives.binary_crossentropy,
                           metrics=["accuracy"])
        self.model.fit(X_train, y_train, epochs=mlp_epoch, shuffle=True, verbose=verbose_level)


    def predict(self, seq):
        features = self.fe.extract_features_using_dict(seq)
        if 'exception' in features.keys():
            return 1
        else:
            se = pd.Series(features)
            se.drop(['ID', 'seq', 'kozak1', 'kozak2'])
            x = np.asarray(se)
            x.shape = (len(se), )
            p = self.model.predict(x)
            p = p[0] # Turn a 1x1 matrix to a scale
            return p


            

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Get the hexmer S-score")
    parser.add_argument(
        '-c', dest='coding_file',
        help='the fasta file of coding transcripts'
    )
    parser.add_argument(
        '-n', dest='non_coding_file',
        help='the fasta file of noncoding transcripts'
    )
    parser.add_argument(
        '-o', dest='output_prefix',
        help='the output file for the S-score matrix'
    )

    args = parser.parse_args()
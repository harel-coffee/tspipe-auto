import numpy as np
import pandas as pd
from sklearn.model_selection import ParameterSampler
from scipy.stats import randint as sp_randint
from scipy.stats import uniform
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn import preprocessing
import matplotlib.pyplot as plt
from numpy.lib.stride_tricks import sliding_window_view
import seaborn as sns
import re
import random
from sklearn.base import clone
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import StratifiedKFold
from src.models.utils import milling_add_y_label_anomaly, under_over_sampler, scale_data, calculate_scores, get_classifier_and_params
from src.models.random_search_setup import general_params
from src.models.classifiers import (
    rf_classifier,
    xgb_classifier,
    knn_classifier,
    lr_classifier,
    sgd_classifier,
    ridge_classifier,
    svm_classifier,
    nb_classifier,
)

from sklearn.metrics import (
    roc_auc_score,
    auc,
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
    roc_curve,
)

from src.models.random_search_setup import (
    rf_params,
    xgb_params,
    knn_params,
    lr_params,
    sgd_params,
    ridge_params,
    svm_params,
    nb_params,
)

from src.visualization.visualize import plot_pr_roc_curves_kfolds


def kfold_cv(df, clf, uo_method, scaler_method, imbalance_ratio, meta_label_cols, stratification_grouping_col=None, y_label_col='y', n_splits=5):

    precisions_list = []
    recalls_list = []
    fpr_list = []
    tpr_list = []
    prauc_list = []
    rocauc_list = []
    f1_list = []

    # perform stratified k-fold cross validation using the grouping of the y-label and another column
    if stratification_grouping_col is not None and stratification_grouping_col is not y_label_col:
        df_strat = df[[stratification_grouping_col, y_label_col]].drop_duplicates()

        skfolds = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        # use clone to do a deep copy of model without copying attached data
        # https://scikit-learn.org/stable/modules/generated/sklearn.base.clone.html
        clone_clf = clone(clf)

        for train_index, test_index in skfolds.split(df_strat[[stratification_grouping_col]], df_strat[['y']]):
            train_strat_vals = df_strat.iloc[train_index][stratification_grouping_col].values
            test_strat_vals = df_strat.iloc[test_index][stratification_grouping_col].values

            x_train = df[df[stratification_grouping_col].isin(train_strat_vals)]
            y_train = x_train[y_label_col].values.astype(int)
            x_train = x_train.drop(meta_label_cols + [y_label_col], axis=1).values

            x_test = df[df[stratification_grouping_col].isin(train_strat_vals)]
            y_test = x_test[y_label_col].values.astype(int)
            x_test = x_test.drop(meta_label_cols + [y_label_col], axis=1).values

            # scale the data
            scale_data(x_train, x_test, scaler_method)

            # under-over-sample the data
            x_train, y_train = under_over_sampler(
                x_train, y_train, method=uo_method, ratio=imbalance_ratio
            )

            # train model
            clone_clf.fit(x_train, y_train)

            # calculate the scores for each individual model train in the cross validation
            # save as a dictionary: "ind_score_dict"
            ind_score_dict = calculate_scores(clone_clf, x_test, y_test)

            precisions_list.append(ind_score_dict['precisions'])
            recalls_list.append(ind_score_dict['recalls'])
            fpr_list.append(ind_score_dict['fpr'])
            tpr_list.append(ind_score_dict['tpr'])
            prauc_list.append(ind_score_dict['prauc_result'])
            rocauc_list.append(ind_score_dict['rocauc_result'])
            f1_list.append(ind_score_dict['f1_result'])
        
    # perform stratified k-fold cross if only using the y-label for stratification 
    else:
        skfolds = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        # use clone to do a deep copy of model without copying attached data
        # https://scikit-learn.org/stable/modules/generated/sklearn.base.clone.html
        clone_clf = clone(clf)

        for train_index, test_index in skfolds.split(df, df[['y']]):
            df_train = df.iloc[train_index]
            df_test = df.iloc[test_index]

            y_train = df_train[y_label_col].values.astype(int)
            x_train = df_train.drop(meta_label_cols + [y_label_col], axis=1).values

            y_test = df_test[y_label_col].values.astype(int)
            x_test = df_test.drop(meta_label_cols + [y_label_col], axis=1).values

            # scale the data
            scale_data(x_train, x_test, scaler_method)

            # under-over-sample the data
            x_train, y_train = under_over_sampler(
                x_train, y_train, method=uo_method, ratio=imbalance_ratio
            )

            # train model
            clone_clf.fit(x_train, y_train)

            # calculate the scores for each individual model train in the cross validation
            # save as a dictionary: "ind_score_dict"
            ind_score_dict = calculate_scores(clone_clf, x_test, y_test)

            precisions_list.append(ind_score_dict['precisions'])
            recalls_list.append(ind_score_dict['recalls'])
            fpr_list.append(ind_score_dict['fpr'])
            tpr_list.append(ind_score_dict['tpr'])
            prauc_list.append(ind_score_dict['prauc_result'])
            rocauc_list.append(ind_score_dict['rocauc_result'])
            f1_list.append(ind_score_dict['f1_result'])       

    precisions_array = np.array(precisions_list, dtype=object)
    recalls_array = np.array(recalls_list, dtype=object)
    fpr_array = np.array(fpr_list, dtype=object)
    tpr_array = np.array(tpr_list, dtype=object)
    prauc_array = np.array(prauc_list, dtype=object)
    rocauc_array = np.array(rocauc_list, dtype=object)
    f1_array = np.array(f1_list, dtype=object)

    # create a dictionary of the result arrays
    result_dict = {"precisions": precisions_array, "recalls": recalls_array, "fpr": fpr_array, 
                "tpr": tpr_array, "prauc": prauc_array, "rocauc": rocauc_array, "f1": f1_array}

    return result_dict


def train_single_model(df, sampler_seed, meta_label_cols, stratification_grouping_col=None, y_label_col='y'):
    # generate the list of parameters to sample over
    train_params = list(
        ParameterSampler(
            general_params, n_iter=1, random_state=sampler_seed
        )
    )[0]

    uo_method = train_params['uo_method']
    scaler_method = train_params['scaler_method']
    imbalance_ratio = train_params['imbalance_ratio']
    classifier = train_params['classifier']
    print(f"classifier: {classifier}, uo_method: {uo_method}, imbalance_ratio: {imbalance_ratio}")

    # get classifier and its parameters
    clf_function, params_clf = get_classifier_and_params(classifier)

    # instantiate the model
    clf, param_dict_clf_raw, param_dict_clf_named = clf_function(sampler_seed, params_clf)
    print("\n", param_dict_clf_raw)

    results_dict = kfold_cv(df, clf, uo_method, scaler_method, imbalance_ratio, meta_label_cols, stratification_grouping_col, y_label_col)

    return results_dict
    
    
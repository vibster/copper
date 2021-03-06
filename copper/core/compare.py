from __future__ import division
import copper
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.metrics import auc
from sklearn import cross_validation
from sklearn.metrics import roc_curve
from sklearn.metrics import confusion_matrix
from sklearn.metrics import mean_squared_error


class ModelComparison():
    '''
    Wrapper around scikit-learn and pandas to make machine learning faster and easier
    Utilities for model selection.
    '''

    def __init__(self):
        self.dataset = None
        self._clfs = {}
        self.costs = [[1,-1],[-1,1]]
        self.feature_labels = None
        self.target_labels = None
        self.X_train = None
        self.y_train = None
        self.X_test  = None
        self.y_test = None

    # --------------------------------------------------------------------------
    #                               PROPERTIES
    # --------------------------------------------------------------------------

    def set_train(self, ds):
        '''
        Uses a Dataset to set the values of inputs and targets for training
        '''
        transformed = copper.transform.inputs2ml(ds)
        self.X_train = transformed.values
        self.feature_labels = transformed.columns
        self.y_train = copper.transform.target2ml(ds).values
        self.target_labels = list(set(self.y_train))

    train = property(None, set_train)

    def set_test(self, ds):
        '''
        Uses a Dataset to set the values of inputs and targets for testing
        '''
        self.X_test = copper.transform.inputs2ml(ds).values
        y_test = copper.transform.target2ml(ds)
        self.y_test = None if y_test is None else y_test.values

    test = property(None, set_test)

    def add_clf(self, clf, name):
        '''
        Adds a new classifier
        '''
        self._clfs[name] = clf

    def add_clfs(self, clfs, prefix):
        '''
        Adds a list of classifiers
        '''
        for i, clf in enumerate(clfs):
            self.add_clf(clf, prefix + '_' + str(i))

    def rm_clf(self, name):
        '''
        Removes a classifier
        '''
        del self._clfs[name]

    def clear_clfs(self):
        '''
        Removes all classifiers
        '''
        self._clfs = {}

    def list_clfs(self):
        '''
        Generates a Series with all the classifiers

        Returns
        -------
            pandas.Series
        '''
        clfs = list(self._clfs.keys())
        values = list(self._clfs.values())
        # func = lambda x: str(type(x))[8:-2]
        # return pd.Series(values, index=clfs).apply(func)
        return pd.Series(values, index=clfs)

    clfs = property(list_clfs, None)

    # --------------------------------------------------------------------------
    #                            Scikit-learn API
    # --------------------------------------------------------------------------

    def fit(self):
        '''
        Fit all the classifiers
        '''
        for clf_name in self.clfs.index:
            self._clfs[clf_name].fit(self.X_train, self.y_train)

    def predict(self, ds=None, clfs=None):
        '''
        Make the classifiers predict the testing inputs

        Parameters
        ----------
            ds: copper.Dataset, dataset fot the prediction, default is self.test
            clfs: list, of classifiers to make prediction, default all

        Returns
        -------
            pandas.DataFrame with the predictions
        '''
        if clfs is None:
            clfs = self.clfs.index
        if ds is not None:
            X_test = copper.transform.inputs2ml(ds).values
        else:
            X_test = self.X_test

        ans = pd.DataFrame(index=range(len(X_test)))
        for clf_name in clfs:
            clf = self._clfs[clf_name]
            scores = clf.predict(X_test)
            new = pd.Series(scores, index=ans.index, name=clf_name, dtype=int)
            ans = ans.join(new)
        return ans

    def predict_proba(self, ds=None, clfs=None):
        '''
        Make the classifiers predict probabilities of inputs
        Parameters
        ----------
            ds: copper.Dataset, dataset fot the prediction, default is self.test
            clfs: list, of classifiers to make prediction, default all

        Returns
        -------
            pandas.DataFrame with the predicted probabilities
        '''
        if clfs is None:
            clfs = self.clfs.index
        if ds is not None:
            X_test = copper.transform.inputs2ml(ds).values
        else:
            X_test = self.X_test

        ans = pd.DataFrame(index=range(len(X_test)))
        for clf_name in clfs:
            clf = self._clfs[clf_name]
            probas = clf.predict_proba(X_test)
            for val in range(np.shape(probas)[1]):
                new = pd.Series(probas[:,val], index=ans.index)
                new.name = '%s [%d]' % (clf_name, val)
                ans = ans.join(new)
        return ans

    def cutoff_predict(self, target=0, cutoff=0.5, ds=None, clfs=None):
        if clfs is None:
            clfs = self.clfs.index

        # Create a list with the indexes of the target columns
        index = self.target_labels.index(target)
        num_options = len(self.target_labels)
        target_cols = [index]
        for row in self.clfs[1:]:
            target_cols.append(target_cols[-1] + num_options)
        
        # Get all the probabilities and get only the columns with target=target
        probas = self.predict_proba(ds=ds, clfs=clfs)
        probas = probas[probas.columns[target_cols]]
        probas.columns = self.clfs.index
        
        for col in probas.columns:
            probas[col][probas[col] < cutoff] = 0
            probas[col][probas[col] > cutoff] = 1
            # break
        return probas


    # --------------------------------------------------------------------------
    #                               METRICS
    # --------------------------------------------------------------------------

    def _metric_wrapper(self, fnc, name='', clfs=None, ascending=False):
        ''' Wraper to not repeat code on all the possible metrics
        '''
        # TODO: generate custom error when X_test is missing
        if clfs is None:
            clfs = self.clfs.index

        ans = pd.Series(index=clfs, name=name)
        for clf_name in clfs:
            clf = self._clfs[clf_name]
            ans[clf_name] = fnc(clf, X_test=self.X_test, y_test=self.y_test)
        return ans.order(ascending=ascending)

    def accuracy(self, **args):
        '''
        Calculates the accuracy of inputs

        Parameters
        ----------
            ascending: boolean, sort the Series on this direction

        Returns
        -------
            pandas.Series with the accuracy
        '''
        def fnc (clf, X_test=None, y_test=None):
            return clf.score(X_test, y_test)

        return self._metric_wrapper(fnc, name='Accuracy', **args)

    def auc(self, **args):
        '''
        Calculates the Area Under the ROC Curve

        Parameters
        ----------
            ascending: boolean, sort the Series on this direction

        Returns
        -------
            pandas.Series with the Area under the Curve
        '''
        def fnc (clf, X_test=None, y_test=None):
            probas = clf.predict_proba(X_test)
            fpr, tpr, thresholds = roc_curve(y_test, probas[:, 1])
            return auc(fpr, tpr)

        return self._metric_wrapper(fnc, name='Area Under the Curve', **args)

    def mse(self, **args):
        '''
        Calculates the Mean Squared Error

        Parameters
        ----------
            ascending: boolean, sort the Series on this direction

        Returns
        -------
            pandas.Series with the Mean Squared Error
        '''
        def fnc (clf, X_test=None, y_test=None):
            y_pred = clf.predict(X_test)
            return mean_squared_error(y_test, y_pred)

        return self._metric_wrapper(fnc, name='Mean Squared Error', ascending=True, **args)


    def rmsle(self, **args):
        '''
        Calculates the Root mean Mean Squared Logaritmic Error (RMSLE)

        Parameters
        ----------
            ascending: boolean, sort the Series on this direction

        Returns
        -------
            pandas.Series with the RMSLE
        '''
        def fnc (clf, X_test=None, y_test=None):
            y_pred = clf.predict(X_test)
            return copper.utils.ml.rmsle(y_test, y_pred)

        return self._metric_wrapper(fnc, name='RMSLE', ascending=True, **args)

    def _cv_metric_wrapper(self, fnc, name='', cv=3, ascending=False):
        ''' Wraper to not repeat code on all the possible crossvalidated metrics
        '''
        # Custom cross_val_score: TODO IPython.Parallel
        # ans = pd.Series(index=self._clfs, name=name)
        # cv = cross_validation.check_cv(cv, self.X_train, self.y_train)
        # for clf_name in self._clfs:
        #     clf = self._clfs[clf_name]            
        #     scores = np.array([])
        #     for train, test in cv:
        #         n_score = fnc(clf,  X_train=self.X_train[train], 
        #                             y_train=self.y_train[train],
        #                             X_test=self.X_train[test],
        #                             y_test=self.y_train[test])
        #         scores = np.append(scores, n_score)
        #         # scores.append(n_score)
        #     ans[clf_name] = np.mean(scores)
        # return ans.order(ascending=ascending)

        # WITH sklearn.cross_val_score
        ans = pd.Series(index=self._clfs, name=name)
        for clf_name in self._clfs:
            clf = self._clfs[clf_name]
            ans[clf_name] = fnc(clf, X=self.X_train, y=self.y_train, cv=cv)
        return ans.order(ascending=ascending)

    def cv_accuracy(self, **args):
        # Custom cross_val_score: TODO IPython.Parallel
        # def fnc (clf, X_train, y_train, X_test, y_test):
        #     clf.fit(X_train, y_train)
        #     return clf.score(X_test, y_test)

        # WITH sklearn.cross_val_score
        def fnc (clf, X, y, cv):
            scores = cross_validation.cross_val_score(clf, X, y, cv=cv)
            return np.mean(scores)
        return self._cv_metric_wrapper(fnc, name='CV Accuracy', **args)


    # --------------------------------------------------------------------------
    #                          Sampling / Crossvalidation
    # --------------------------------------------------------------------------

    def sample(self, ds, train_size=0.5):
        '''
        Samples the dataset into training and testing

        Parameters
        ----------
            ds: copper.Dataset, to use to sample, default, self.dataset
            trainSize: int, percent of the dataset to be used to training,
                                        the remaining will be used to testing

        Returns
        -------
            nothing, self.X_train, self.y_train, self.X_test, self.y_test are set
        '''
        transformed = copper.transform.inputs2ml(ds)
        inputs = transformed.values
        self.feature_labels = transformed.columns
        target = copper.transform.target2ml(ds).values
        self.target_labels = list(set(target))

        X_train, X_test, y_train, y_test = cross_validation.train_test_split(
                        inputs, target,
                        test_size=(1-train_size))
        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test

    # --------------------------------------------------------------------------
    #                            CONFUSION MATRIX
    # --------------------------------------------------------------------------

    def _cm(self, clfs=None):
        '''
        Calculates the confusion matrixes of the classifiers

        Parameters
        ----------
            clfs: list or str, of the classifiers to calculate the cm

        Returns
        -------
            python dictionary
        '''
        if clfs is None:
            clfs = self._clfs.keys()
        else :
            if type(clfs) is str:
                clfs = [clfs]

        ans = {}
        for clf_name in clfs:
            clf = self._clfs[clf_name]
            y_pred = clf.predict(self.X_test)
            ans[clf_name] = confusion_matrix(self.y_test, y_pred)
        return ans

    def cm(self, clf):
        '''
        Return a pandas.DataFrame version of a confusion matrix

        Parameters
        ----------
            clf: str, classifier identifier
        '''
        cm = self._cm(clfs=clf)[clf]
        values = set(self.y_test)
        return pd.DataFrame(cm, index=values, columns=values)

    def cm_table(self, values=None, ascending=False):
        '''
        Returns a more information about the confusion matrix

        Parameters
        ----------
            value: int, target value of the target variable. For example if the
                        target variable is binary (0,1) value can be 0 or 1.
            ascending: boolean, list sorting direction

        Returns
        -------
            pandas.DataFrame
        '''
        if values is None:
            values = set(self.y_test)
        elif type(values) is int:
            values = [values]

        cm_s = self._cm()
        ans = pd.DataFrame(index=cm_s.keys())
        zeros = np.zeros((len(ans), 3))

        for value in values:
            cols = ['Predicted %d\'s' % value, 'Correct %d\'s' % value,
                                    'Rate %d\'s' % value]
            n_ans = pd.DataFrame(zeros ,index=cm_s.keys(), columns=cols)
            for clf_name in cm_s.keys():
                cm = cm_s[clf_name]
                n_ans['Predicted %d\'s' % value][clf_name] = cm[:,value].sum()
                n_ans['Correct %d\'s' % value][clf_name] = cm[value,value].sum()
                n_ans['Rate %d\'s' % value][clf_name] = cm[value,value].sum() / cm[:,value].sum()
            ans = ans.join(n_ans)
        return ans.sort_index(by='Rate %d\'s' % value, ascending=ascending)

    def cm_falses(self):
        # TODO: like above but for false negative, false positive
        pass

    # --------------------------------------------------------------------------
    #                                 COSTS
    # --------------------------------------------------------------------------

    def profit(self, by='Profit', ascending=False):
        '''
        Calculates the Revenue of using the classifiers.
        self.costs should be modified to get better information.

        Parameters
        ----------
            by: str, sort the DataFrame by. Options are: Loss from False Positive, Revenue, Profit
            ascending: boolean, Sort the DataFrame by direction

        Returns
        -------
            pandas.DataFrame
        '''
        cm_s = self._cm()
        cols = ['Loss from False Positive', 'Revenue', 'Profit']
        ans = pd.DataFrame(np.zeros((len(cm_s.keys()), 3)), index=cm_s.keys(), columns=cols)

        for clf in ans.index:
            cm = cm_s[clf]
            ans['Loss from False Positive'][clf] = cm[0,1] * self.costs[0][1]
            ans['Revenue'][clf] = cm[1,1] * self.costs[1][1]
            ans['Profit'][clf] = ans['Revenue'][clf] - \
                                        ans['Loss from False Positive'][clf]

        return ans.sort_index(by=by, ascending=ascending)

    def oportunity_cost(self, ascending=False):
        '''
        Calculates the Oportuniy Cost of the classifiers.
        self.costs should be modified to get better information.

        Parameters
        ----------
            ascending: boolean, Sort the Series by direction

        Returns
        -------
            pandas.DataFrame
        '''
        cm_s = self._cm()
        ans = pd.Series(index=cm_s.keys(), name='Oportuniy cost')

        for clf in ans.index:
            cm = cm_s[clf]
            ans[clf] = cm[1,0] * self.costs[1][0] + cm[0,1] * self.costs[0][1]
        return ans.order(ascending=ascending)

    def cost_no_ml(self, ascending=False):
        '''
        Calculate the revenue of not using any classifier.
        self.costs should be modified to get better information.

        Parameters
        ----------
            ascending: boolean, Sort the DataFrame by direction

        Returns
        -------
            pandas.Series
        '''
        cols = ['Expense', 'Revenue', 'Net revenue']
        ans = pd.Series(index=cols, name='Costs of not using ML')

        # TODO: replace for bincount
        # counts = np.bincount(self.y_test)
        counts = []
        counts.append(len(self.y_test[self.y_test == 0]))
        counts.append(len(self.y_test[self.y_test == 1]))
        ans['Expense'] = counts[0] * self.costs[1][0]
        ans['Revenue'] = counts[1] * self.costs[1][1]
        ans['Net revenue'] = ans['Revenue'] - ans['Expense']

        return ans.order(ascending=ascending)

    # --------------------------------------------------------------------------
    #                                 PLOTS
    # --------------------------------------------------------------------------

    def roc(self, ascending=False, legend=True, ret_list=False):
        '''
        Plots the ROC chart

        Parameters
        ----------
            legend: boolean, if want the legend on the chart
            ret_list: boolean, True if want the method to return a list with the
                            areas under the curve
            ascending: boolean, legend and list sorting direction

        Returns
        -------
            nothing, the plot is ready to be shown
        '''
        aucs = self.auc(ascending=ascending)
        for clf_name in aucs.index:
            clf = self._clfs[clf_name]
            try:
                probas_ = clf.predict_proba(self.X_test)
                fpr, tpr, thresholds = roc_curve(self.y_test, probas_[:, 1])
                plt.plot(fpr, tpr, label='%s (area = %0.2f)' % (clf_name, aucs[clf_name]))
            except:
                pass # Is OK, some models do not have predict_proba

        plt.plot([0, 1], [0, 1], 'k--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.0])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('ROC: Receiver operating characteristic')

        if legend:
            # plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
            plt.legend(loc='best')
        if ret_list:
            return aucs

    def plot_cm(self, clf):
        '''
        Plots the confusion matrixes of the classifier

        Parameters
        ----------
            clf: str, classifier identifier
            X_test: np.array, inputs for the prediction, default is self.X_test
            y_test: np.array, targets for the prediction, default is self.y_test
            ds: copper.Dataset, dataset for the prediction, default is self.test
        '''
        plt.matshow(self.cm(clf))
        plt.title('%s Confusion matrix' % clf)
        plt.colorbar()


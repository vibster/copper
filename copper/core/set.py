from __future__ import division
import os
import io
import json
import copper
import numpy as np
import pandas as pd

class Dataset(dict):
    '''
    Wrapper around pandas to define metadata to a pandas DataFrame.
    Also introduces a some utils for filling missing data, statistics and ploting.
    '''
    ID = 'ID'
    INPUT = 'Input'
    TARGET = 'Target'
    NUMBER = 'Number'
    REJECT = 'Reject'
    REJECTED = 'Reject'
    CATEGORY = 'Category'

    def __init__(self, data=None):
        '''
        Creates a new Dataset

        Parameters
        ----------
            data: str with the path of the data. Or pandas.DataFrame.
        '''
        self._frame = None
        self.pca_model = None

        if data is not None:
            if type(data) is pd.DataFrame:
                self.frame = data
            elif type(data) is str:
                self.load(data)

    # --------------------------------------------------------------------------
    #                                 LOAD
    # --------------------------------------------------------------------------

    def _id_identifier(self, col_name):
        '''
        Indentifier for Role=ID based on the name of the column
        '''
        return str(col_name).lower() in ['id']

    def _target_identifier(self, col_name):
        '''
        Indentifier for Role=Target based on the name of the column
        '''
        return str(col_name).lower() in ['target']

    def load(self, file_path):
        ''' Loads a csv file from the project data directory.

        Parameters
        ----------
            file_path: str
        '''
        filepath = os.path.join(copper.project.data, file_path)
        self.frame = pd.read_csv(filepath)

    # --------------------------------------------------------------------------
    #                                PROPERTIES
    # --------------------------------------------------------------------------

    def set_frame(self, frame, metadata=True):
        ''' Sets the frame of the Dataset and Generates metadata for the frame

        Parameters
        ----------
            frame: pandas.DataFrame
        '''
        self._frame = frame
        self.columns = self._frame.columns.values
        self.role = pd.Series(index=self.columns, name='Role', dtype=str)
        self.type = pd.Series(index=self.columns, name='Type', dtype=str)

        # Roles
        id_cols = [c for c in self.columns if self._id_identifier(c)]
        if len(id_cols) > 0:
            self.role[id_cols] = 'ID'

        target_cols = [c for c in self.columns if self._target_identifier(c)]
        if len(target_cols) > 0:
            # Set only variable to be target
            self.role[target_cols[0]] = self.TARGET
            self.role[target_cols[1:]] = self.REJECTED

        rejected = self.percent_missing()[self.percent_missing() > 0.5].index
        self.role[rejected] = self.REJECTED
        self.role = self.role.fillna(value=self.INPUT) # Missing cols are Input

        # Types
        number_cols = [c for c in self.columns
                            if self._frame.dtypes[c] in (np.int64, np.float64)]
        self.type[number_cols] = self.NUMBER
        self.type = self.type.fillna(value=self.CATEGORY)

    def get_frame(self):
        return self._frame

    frame = property(get_frame, set_frame)

    def get_index(self):
        return self._frame.index

    index = property(get_index)

    def get_inputs(self):
        ''' Return a DataFrame with the colums with role=INPUT

        Returns
        -------
            df: pandas.DataFrame
        '''
        ans = self.filter(role=self.INPUT)
        return None if ans.empty else ans

    inputs = property(get_inputs)

    def get_target(self):
        ''' Returns a DataFrame with the first column with role=TARGET

        Returns
        -------
            df: pandas.Series
        '''
        ans = self.filter(role=self.TARGET)
        return None if ans.empty else ans[[ans.columns[0]]]

    target = property(get_target)

    def get_numerical(self):
        ''' Returns a DataFrame with the first column with type=NUMBER
        '''
        ans = self.filter(type=self.NUMBER)
        return None if ans.empty else ans

    numerical = property(get_numerical)

    def get_categorical(self):
        ''' Returns a DataFrame with the first column with type=CATEGORY
        '''
        ans = self.filter(type=self.CATEGORY)
        return None if ans.empty else ans

    categorical = property(get_categorical)

    def get_metadata(self):
        ''' Returns a DataFrame with the metadata

        Returns
        -------
            pandas.DataFrame with the role and type of each column
        '''
        metadata = pd.DataFrame(index=self.columns)
        metadata['Role'] = self.role
        metadata['Type'] = self.type
        metadata['dtype'] = self._frame.dtypes
        return metadata

    metadata = property(get_metadata)

    # --------------------------------------------------------------------------
    #                             FUNCTIONALITY
    # --------------------------------------------------------------------------

    def update(self):
        ''' Updates the frame based on the metadata
        '''
        for col in self._frame.columns:
            if self.type[col] == self.NUMBER and \
                                        self._frame[col].dtype == object:
                self._frame[col] = self._frame[col].apply(copper.transform.to_number)

    def save(self, filename):
        copper.save(self, filename)

    def filter(self, role=None, type=None, ret_cols=False, ret_ds=False):
        ''' Filter the columns of the Dataset by Role and Type

        Parameters
        ----------
            role: Role constant
            type: Type constant
            columns: boolean, True if want only the column names

        Returns
        -------
            pandas.DataFrame
        '''
        # Note on this funcion python.type(...) is replaced by the type argument
        def _type(obj):
            return obj.__class__
        if role is None:
            role = [self.ID, self.INPUT, self.TARGET, self.REJECTED]
        elif _type(role) == str:
            role = [role]

        if type is None:
            type = [self.NUMBER, self.CATEGORY]
        elif _type(type) == str:
            type = [type]

        cols = [col for col in self.columns.tolist() 
                        if self.role[col] in role and self.type[col] in type]
        
        if ret_cols:
            return cols
        elif ret_ds:
            ds = Dataset(self._frame[cols])
            ds.match(self)
            return ds
        else:
            return self._frame[cols]

    def fix_names(self):
        '''  Removes spaces and symbols from column names
        Those symbols generates error if using patsy
        '''
        # TODO: change to regexp
        new_cols = self.columns.tolist()
        symbols = ' .-'
        for i, col in enumerate(new_cols):
            for symbol in symbols:
                new_cols[i] = ''.join(new_cols[i].split(symbol))
        self._frame.columns = new_cols
        self.columns = new_cols
        self.role.index = new_cols
        self.type.index = new_cols

    def match(self, other_ds):
        ''' Makes this Dataset match other Dataset metadata
        '''
        self.role[:] = other_ds.REJECTED
        for col in self.columns:
            try :
                self.role[col] = other_ds.role[col]
                self.type[col] = other_ds.type[col]
            except:
                pass # This can happen is some col is not on the other ds

    def join(self, other_ds, how='outer'):
        ans = self.frame.join(other_ds.frame)
        ans = Dataset(ans)

        for index, row in self.metadata.iterrows():
            ans.role[index] = row['Role']
            ans.type[index] = row['Type']
        for index, row in other_ds.metadata.iterrows():
            ans.role[index] = row['Role']
            ans.type[index] = row['Type']

        return ans

    def fillna(self, cols=None, method='mean', value=None):
        '''
        Fill missing values

        Parameters
        ----------
            cols: list, of columns to fill missing values
            method: str, method to use to fill missing values
                * mean(numerical,money)/mode(categorical): use the mean or most
                  repeted value of the column
                * knn
        '''
        if cols is None:
            cols = self.columns
        elif type(cols) is not list:
            cols = [cols]

        if method == 'mean' or method == 'mode':
            for col in cols:
                if self.role[col] == self.INPUT:
                    if self.type[col] == self.NUMBER:
                        value = self[col].mean()
                    if self.type[col] == self.CATEGORY:
                        value = self[col].value_counts().index[0]
                    self[col] = self[col].fillna(value=value)
        elif method == 'knn':
            # TODO: FIX
            for col in cols:
                imputed = copper.r.imputeKNN(self._frame)
                self._frame[col] = imputed[col]
        elif value is not None:
            for col in cols:
                if self.role[col] != self.REJECTED:
                    if type(value) is str:
                        if self.role[col] != self.CATEGORY:
                            self[col] = self[col].fillna(value=value)
                    elif type(value) is int or type(value) is float:
                        if self.role[col] != self.NUMBER:
                            self[col] = self[col].fillna(value=value)

    # --------------------------------------------------------------------------
    #                                    STATS
    # --------------------------------------------------------------------------

    def unique_values(self, role=None, type=None, ascending=False):
        '''
        Generetas a Series with the number of unique values of each column
        Note: Excludes NA

        Parameters
        ----------
            ascending: boolean, sort the returned Series on this direction

        Returns
        -------
            pandas.Series
        '''
        data = self.filter(role=role, type=type)
        return copper.utils.frame.unique_values(data, ascending=ascending)

    def percent_missing(self, role=None, type=None, ascending=False):
        '''
        Generetas a Series with the percent of missing values of each column

        Parameters
        ----------
            ascending: boolean, sort the returned Series on this direction

        Returns
        -------
            pandas.Series
        '''
        data = self.filter(role=role, type=type)
        return copper.utils.frame.percent_missing(data, ascending=ascending)

    def corr(self, cols=None, limit=None, two_tails=False, ascending=False):
        ''' Correlation between inputs and target
        If a column has a role of target only the correlations to that colum 
        are returned.
        If not columns have a role of target then the pandas.corr is called 
        on the inputs.

        Parameters
        ----------
            cols: list, list of columns on the returned DataFrame.
                        default=None: On that case if there is a column with
                        role=Target then retuns only values for that column if
                        there is not return all values
            cols: str, special case: 'all' to return all values

        Returns
        -------
        '''
        if cols is None:
            try :
                # If there is a target column use that
                cols = self.role[self.role == self.TARGET].index[0]
            except:
                # If not use number cols
                cols = [c for c in self.columns
                              if self._frame.dtypes[c] in (np.int64, np.float64)]
        elif cols == 'all':
            cols = [c for c in self.columns
                              if self._frame.dtypes[c] in (np.int64, np.float64)]

        corrs = self._frame.corr()
        corrs = corrs[cols]
        if type(corrs) is pd.Series:
            corrs = corrs[corrs.index != cols]

            if limit is not None:
                if two_tails:
                    corrs = corrs[(corrs >= abs(limit)) | (corrs <= -abs(limit))]
                else:
                    if limit < 0:
                        corrs = corrs[corrs <= -abs(limit)]
                    else:
                        corrs = corrs[corrs >= abs(limit)]



            return corrs.order(ascending=ascending)
        else:
            return corrs

    def skew(self, role=None, type=None, ascending=False):
        data = self.filter(role=role, type=type)
        return data.skew().order(ascending=ascending)
        # return self._frame.skew().order(ascending=ascending)

    def outlier_count(self, **args):
        data = self.filter(role=self.INPUT, type=self.NUMBER)
        return copper.utils.frame.outlier_count(data, **args)

    def features_weight(self, **args):
        X = copper.transform.inputs2ml(self)
        y = copper.transform.target2ml(self)
        return copper.utils.frame.features_weight(X, y, **args)

    def rce_rank(self, **args):
        X = copper.transform.inputs2ml(self)
        y = copper.transform.target2ml(self)
        return copper.utils.frame.rce_rank(X, y, **args)
    
    def PCA(self, **args):
        X = copper.transform.inputs2ml(self)
        values, pca_model = copper.utils.frame.PCA(X, ret_model=True, **args)

        frame = pd.DataFrame(values)
        if self.target is not None:
            frame = frame.join(self.target)
        
        ds = copper.Dataset(frame)
        if self.target is not None:
            ds.role[self.filter(role=self.TARGET, ret_cols=True)] = self.TARGET
        ds.pca_model = pca_model
        return ds

    def match_pca(self, ds):
        values = copper.transform.inputs2ml(self).values
        values = ds.pca_model.transform(values)
        frame = pd.DataFrame(values)
        if self.target is not None:
            frame = frame.join(self.target)
        ds = copper.Dataset(frame)
        if self.target is not None:
            ds.role[self.filter(role=ds.TARGET, ret_cols=True)] = self.TARGET    
        return ds
    # --------------------------------------------------------------------------
    #                                    CHARTS
    # --------------------------------------------------------------------------

    def plot(self, kind=None, col=None, col2=None, col3=None, **args):
        if kind is None:
            return
        if kind == 'hist' or kind == 'histogram':
            return self.histogram(col, **args)
        if kind == 'scatter':
            return self.scatter(col, col2, col3, **args)

    def histogram(self, col, **args):
        '''
        Draws a histogram for the selected column on matplotlib

        Parameters
        ----------
            col:str, column name
            bins: int, number of bins of the histogram, default 20
            legend: boolean, True if want to display the legend of the ploting
            ret_list: boolean, True if want the method to return a list with the
                                distribution(information) of each bin

        Return
        ------
            nothing, figure is ready to be shown
        '''
        return copper.plot.histogram(self._frame[col], **args)

    def scatter(self, col1, col2, col3, **args):
        copper.plot.scatter(self.frame, col1, col2, col3, **args)

    def scatter_pca(self):
        X = copper.transform.inputs2ml(self)
        y = copper.transform.target2ml(self)
        copper.plot.scatter_pca(X, y)

    # --------------------------------------------------------------------------
    #                    SPECIAL METHODS / PANDAS API
    # --------------------------------------------------------------------------

    def __unicode__(self):
        return self.metadata

    def __str__(self):
        return str(self.__unicode__())

    def __getitem__(self, name):
        return self._frame[name]

    def __setitem__(self, name, value):
        self._frame[name] = value

    def __len__(self):
        return len(self._frame)

    def head(self, n=5):
        return self._frame.head(n)

    def tail(self, n=5):
        return self._frame.tail(n)

    def get_values(self):
        ''' Returns the values of the dataframe
        '''
        return self._frame.values

    values = property(get_values)

    def describe(self):
        return self._frame.describe()

def join(ds1, ds2, others=[], how='outer'):
    others.insert(0, ds2)
    others.insert(0, ds1)

    df = None
    for ds in others:
        if df is not None:
            df = df.join(ds.frame, how=how)
        else:
            df = ds.frame

    ans = Dataset(df)
    for ds in others:
        for index, row in ds.metadata.iterrows():
            ans.role[index] = row['Role']
            ans.type[index] = row['Type']

    return ans
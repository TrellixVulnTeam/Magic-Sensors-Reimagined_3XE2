""" 
	File: tf_model_handler.py

	Function: This file is meant to act as a means for the server to 
	interacts with our deep learning model. While it may seem like there
	are two thread, the function creates the second thread is invoked by
	a function running on the server's main thread. In future iterations,
	I may add a second thread to do training on, however given that we 
	won't want to interrupt training after it has begun, blocking the 
	handler thread may be the best course of action.

	--------------------------------------------------------------------
	General Training Flow (Assuming inital training or retraining)

	1. End user checks the current state of the of the model as specified
	by the API. NOTE: Only if the current state is MODEL_DOESNT_EXIST or
	FINISHED_TRAINING should the user continue to step 2.

	2. End user starts training by making the specified API call. Invoking
	this function will change the model state to START_TRAINING.

	3. Once moved to START_TRAINING, the handler thread will initialize
	all necessary resources required for training. Once the data is 
	preprocessed and ready to be trained with, the model state will 
	change to TRAINING_IN_PROGRESS.

	4. While in TRAINING_IN_PROGRESS, the end user will not be able to 
	request a copy of the deep learning model. During this state, the
	handler thread will be blocked until training has completed. This
	is to prevent potential corruption of the model due to partial
	training. Following training completion, the state will be moved
	to FINISHED_TRAINING.

	5. Once in FINISHED_TRAINING, it would be appropriate for the end
	user to request a copy of the new model. (Potential feature: API 
	call that will return a hash of the current model so the end user
	can check to see if their local model is up-to-date). The handler
	thread will remain in the FINISHED_TRAINING state until it is 
	requested by the end user to train again.
	--------------------------------------------------------------------
	
	Recommenend implementation on the pi:

	1. Create a thread specifically for handling training user the FSM
	model as used here.

	2. In the training thread, invoke the training API call once the
	training data set has been gathered.

	3. From this point, do a time.sleep(30). After the thread wakes
	up, query the API for the current state of the model. If it's still
	in TRAINING_IN_PROGRESS, go back to sleep for 30 seconds. Repeat 
	until the query returns FINISHED_TRAINING.

	4. Once the model has finished training, make a request for the 
	newly trained model. Overwrite the currently implemented model
	with the new model.
"""

import time
import random
from enum import Enum
import logger
from threading import Thread

import numpy as np
import pandas
from keras.models import Sequential
from keras.layers import Dense
from keras.wrappers.scikit_learn import KerasClassifier
from keras.utils import np_utils
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import KFold
from contextlib import redirect_stdout
import sys

__author__ = "Ryan Lanciloti"
__credits__ = ["Ryan Lanciloti"]
__version__ = "1.0.10"
__maintainer__ = "Ryan Lanciloti"
__email__ = ["ryanjl9@iastate.edu", "rlanciloti@outlook.com"]
__status__ = "Development"

class MLTrainingStates(Enum):
	""" This is the enum that will dictate the states that our model
	will transition through while training.

	MODEL_DOESNT_EXIST: Before we generate the model for the first time
	or if we have to delete the model for any reason, this ensures that
	the front end server doesn't accidentally try to pull non-existant 
	data.

	START_TRAINING: This state will act as a flag to kick off training
	the model. TRAINING_STATE will only ever be set to this state by our server
	as training has to be requested.

	TRAINING_IN_PROGRESS: While training is happening, this will act
	as a flag for both the front-end and back-end servers. If we are
	currently training, wait until it has finished.

	FINISHED_TRAINING: We will only ever enter this state once the 
	model is ready to be sent to the front-end server. When we enter
	this state, we will also set the total time that training took 
	for metrics if wanted.

	"""
	MODEL_DOESNT_EXIST = 0
	START_TRAINING = 1
	TRAINING_IN_PROGRESS = 2
	FINISHED_TRAINING = 3
	TRAINING_FAILED = 4


class MLInferencingStates(Enum):
	MODEL_STILL_LOADING = 0
	INFERENCING_AVAILABLE = 1
	INFERENCING_IN_PROGRESS = 2


""" For testing purposed, until we have a model, we're going to set
the state to FINISHED_TRAINING. Later on, when we have a model,
we will check if the model exists or not. If not, we will set the
state to MODEL_DOESNT_EXIST, otherwise FINISHED_TRAINING given
we can assume we've successfully trained the model.
"""

TRAINING_STATE = MLTrainingStates.MODEL_DOESNT_EXIST
INFERENCING_STATE = MLInferencingStates.MODEL_STILL_LOADING
TRAINING_TIME = 0.0
TRAINING_DATA = []
DATA_TYPE = "NOT_SET"
ESTIMATOR_M = None
ESTIMATOR_P = None
ENCODER = None
DATA_AVAILABLE = False
INFERENCING_DATA = []
PREDICTION = ()
TEST_DATA_PREDICTION = ()
TRAINING_FAILURE_ERROR = "<TRAINING NOT FAILED YET>"

def _thread_training_handler():
	""" This function is responsible for handling the machine learning
	thread. This may only act as a state machine or it may be the thread
	that tensorflow runs on.
	"""
	global TRAINING_STATE
	global TRAINING_TIME
	global ESTIMATOR_M
	global ESTIMATOR_P
	global ENCODER
	global TEST_DATA_PREDICTION

	tt_start = 0.0

	while(True):
		if TRAINING_STATE == MLTrainingStates.START_TRAINING:
			tt_start = time.time()
			logger.info("\nStarting Training\n")
			TRAINING_TIME = 0.0
			TRAINING_STATE = MLTrainingStates.TRAINING_IN_PROGRESS
		
		if TRAINING_STATE == MLTrainingStates.TRAINING_IN_PROGRESS:

			try:
				seed = 7
				np.random.seed(seed)

				dataframe = pandas.read_csv("TrainingNoChairs.csv", header=0)
				dataset = dataframe.values
				X_mag = dataset[:,1:54].astype(float)
				X_phase = dataset[:,54:107].astype(float)
				Y = dataset[:,0]

				logger.info("\nModel Read In\n")

				# assign integer to each class
				ENCODER = LabelEncoder()
				ENCODER.fit(Y)
				encoded_Y = ENCODER.transform(Y)
				logger.info("\nEncoder Fit done\n")

				# one hot encoding
				dummy_y = np_utils.to_categorical(encoded_Y)

		
				ESTIMATOR_M = KerasClassifier(build_fn=baseline_model, epochs=250, batch_size=5, verbose=0)
				ESTIMATOR_P = KerasClassifier(build_fn=baseline_model, epochs=250, batch_size=5, verbose=0)

				X_train_m, X_test_m, Y_train_m, Y_test_m = train_test_split(X_mag, dummy_y, test_size=0.1, random_state=seed)
				X_train_p, X_test_p, Y_train_p, Y_test_p = train_test_split(X_phase, dummy_y, test_size=0.1, random_state=seed)

				logger.info("\nEstimator Fit Starting\n")
				with open("fit_redirect.txt", "w+") as f:
					with redirect_stdout(f):
						ESTIMATOR_M.fit(X_train_m, Y_train_m, verbose=2)
						f.flush()
						ESTIMATOR_P.fit(X_train_p, Y_train_p, verbose=2)
						f.flush()
				logger.info("\nEstimator Fit Done\n")

				predictions_m = ESTIMATOR_M.predict(X_test_m)
				predictions_m = ENCODER.inverse_transform(predictions_m)
				predictions_classes_m = ESTIMATOR_M.predict_proba(X_test_m)

				predictions_p = ESTIMATOR_P.predict(X_test_p)
				predictions_p = ENCODER.inverse_transform(predictions_p)
				predictions_classes_p = ESTIMATOR_P.predict_proba(X_test_p)

				TEST_DATA_PREDICTION = (predictions_m, predictions_classes_m,
							  			predictions_p, predictions_classes_p)

				TRAINING_TIME = time.time() - tt_start
				TRAINING_STATE = MLTrainingStates.FINISHED_TRAINING
				logger.info("\nTraining Over\n")
			except Exception as e:
				logger.error(f"\nSomething Broke: {e}")
				TRAINING_STATE = MLTrainingStates.TRAINING_FAILED
				TRAINING_FAILURE_ERROR = str(e)
		
		if TRAINING_STATE == MLTrainingStates.FINISHED_TRAINING:
			pass


def _thread_inferencing_handler():
	"""
	"""
	global INFERENCING_STATE
	global TRAINING_STATE
	global INFERENCING_DATA
	global PREDICTION
	global DATA_AVAILABLE
	global ESTIMATOR_M
	global ESTIMATOR_P

	while(True):
		if INFERENCING_STATE == MLInferencingStates.MODEL_STILL_LOADING and \
		   TRAINING_STATE == MLTrainingStates.FINISHED_TRAINING:
			INFERENCING_STATE = MLInferencingStates.INFERENCING_AVAILABLE
			logger.info("\nModel Still Loading\n")

		if INFERENCING_STATE == MLInferencingStates.INFERENCING_AVAILABLE and \
		   DATA_AVAILABLE:
			logger.info("Data Available")
			INFERENCING_STATE = MLInferencingStates.INFERENCING_IN_PROGRESS

		if INFERENCING_STATE == MLInferencingStates.INFERENCING_IN_PROGRESS:
			try:
				logger.info("Beginning Inference")
				logger.info(f"Inferencing Data - {INFERENCING_DATA}")
				m_arr = np.array(INFERENCING_DATA[0:53]).reshape(1,53)
				p_arr = np.array(INFERENCING_DATA[53:106]).reshape(1,53)
				DATA_AVAILABLE = False

				predictions_m = ESTIMATOR_M.predict(m_arr)
				predictions_m = ENCODER.inverse_transform(predictions_m)
				predictions_classes_m = ESTIMATOR_M.predict_proba(m_arr)

				predictions_p = ESTIMATOR_P.predict(p_arr)
				predictions_p = ENCODER.inverse_transform(predictions_p)
				predictions_classes_p = ESTIMATOR_P.predict_proba(p_arr)

				PREDICTION = (predictions_m, predictions_classes_m,
							  predictions_p, predictions_classes_p)
				logger.info(PREDICTION)
				INFERENCING_STATE = MLInferencingStates.INFERENCING_AVAILABLE

			except Exception as e:
				logger.info(f"Error: {e}")


def baseline_model():
	model = Sequential()
	model.add(Dense(24, input_dim=53, activation='relu'))
	model.add(Dense(7, activation='softmax')) # normalizes output to 1

	model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])
	return model


def init_tf_handler():
	""" This function will be responsible for setting up the handler. 
	Here is where we'd do the check to see if the model exists or not.
	"""

	global TRAINING_STATE
	global TRAINING_TIME
	global TRAINING_DATA
	global INFERENCING_STATE
	global DATA_TYPE

	TRAINING_STATE = MLTrainingStates.START_TRAINING
	TRAINING_TIME = 0.0
	TRAINING_DATA = []
	DATA_TYPE = "NOT_SET"

	training_state_machine = Thread(target=_thread_training_handler, args=())
	inferencing_state_machine = Thread(target=_thread_inferencing_handler, args=())
	training_state_machine.start()
	inferencing_state_machine.start()
	
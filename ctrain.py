# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.10.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
import numpy as np
from keras.datasets import fashion_mnist
from tqdm import tqdm
import matplotlib.pyplot as plt
import math
import wandb
import cupy as cp

# %%
current_wandb_run = wandb.init(project = "fdl-a1",entity = "fdl-thops",config = {"dataset":"fashion_mnist","input_size":784,\
                    "output_size":10,"hidden_layers":[16,16],"epochs":10,"learning_rate":0.01,\
                    "batch_size":32,"initialization_type":"xavier","activation":"sigmoid",\
                    "optimiser":"nadam","gamma":0.1,"train_test_split":0.2,"seed":None,"beta":0.99,\
                    "epsilon":0.0000001,"beta1":0.9,"beta2":0.999,"l2_reg_param":0,"init_params":True,\
                    "hidden_1":128,"hidden_2":128,"hidden_3":128,"hidden_4":128,"hidden_5":128})


# %%
class NeuralNet:

    @staticmethod
    def sigmoid(X):
        X = cp.clip( X, -700, 700)
        return 1 / (1. + cp.exp(-X))
            
    @staticmethod
    def tanh(X):
        X = cp.clip( X, -350, 350)
        return (1 - cp.exp(-2*X)) / (1 + cp.exp(-2*X))
        
        
    @staticmethod
    def relu(X):
        return cp.where( X<0, 0, X)
        
    @staticmethod
    def activate( X, activation = "sigmoid"):
        if activation == "sigmoid":
            return NeuralNet.sigmoid(X)
        elif activation == "tanh":
            return NeuralNet.tanh(X)
        elif activation == "relu":
            return NeuralNet.relu(X)
        else:
            raise(ValueError("Unknown activation \"" + activation + "\""))

    def __init__( self, input_size, output_size = 2):
        self.structure = [ input_size, output_size]
        self.params = {}
        self.optimisers = {"sgd":self.do_sgd,"momentum":self.do_momentum,"nesterov":self.do_nesterov,\
                           "rmsprop":self.do_rmsprop,"adam":self.do_adam,"nadam":self.do_nadam}
        
    def addlayer( self, layer_size):
        self.structure = self.structure[:-1] + [ layer_size, self.structure[-1]]
        
    def initialise_params( self, initialization_type = "random"):
        self.init_type = initialization_type
        if self.init_type == "random":
            for i in range( 1, len(self.structure)):
                self.params["w"+str(i)] = cp.random.rand( self.structure[i], self.structure[i-1]) - 0.5
                self.params["b"+str(i)] = cp.random.rand( self.structure[i], 1) - 0.5
        elif self.init_type == "xavier":
            for i in range(1,len(self.structure)):
                self.params["w"+str(i)] = cp.random.normal(0,1/cp.sqrt(self.structure[i-1]+\
                                                    self.structure[i]),(self.structure[i],self.structure[i-1]))
                self.params["b"+str(i)] = cp.random.normal(0,1/cp.sqrt(self.structure[i-1]+\
                                                    self.structure[i]),(self.structure[i],1))
        else:
            print(self.init_type + ": unidentified initialization type")    
    
    @staticmethod
    def activation_gradient( A, activation = "sigmoid"):
        if activation == "sigmoid":
            return cp.multiply(A,(1-A))
        elif activation == "tanh":
            return 1 - cp.square(A)
        elif activation == "relu":
            A[A>0] = 1
            A[A<0] = 0
            return A
        else:
            raise(ValueError("Unknown activation \"" + activation + "\""))

    def calculate_grads( self, X, Y, l2_reg_param):
        grads = {}
        values = self.predict(X,returndict=1)
        layers = len(self.structure)-1
        nsamples = X.shape[1]
        grads["a"+str(layers)] = -(cp.eye(self.structure[-1])[Y]).T + values["h"+str(layers)]
        for ii in cp.arange(layers-1,0,-1):
            grads["h"+str(ii)] = cp.matmul(self.params["w"+str(ii+1)].T,grads["a"+str(ii+1)])
            grads["a"+str(ii)] = cp.multiply(grads["h"+str(ii)],self.activation_gradient(values["h"+str(ii)],self.activation))
        for ii in cp.arange(layers,0,-1):
            grads["w"+str(ii)] = cp.matmul((grads["a"+str(ii)].T).reshape(nsamples,-1,1),\
                                    (values["h"+str(ii-1)].T).reshape(nsamples,1,-1)) \
                                    + (l2_reg_param/nsamples) * self.params["w"+str(ii)]
            grads["b"+str(ii)] = grads["a"+str(ii)]
        return grads

    def do_sgd( self, X, Y, update, learning_rate, **kwargs):
        layers = len(self.structure)-1
        grads = self.calculate_grads(X,Y,kwargs["l2_reg_param"])
        for ii in cp.arange(1,layers+1):
            self.params["w"+str(ii)] -= learning_rate * cp.sum(grads["w"+str(ii)],axis=0)
            self.params["b"+str(ii)] -= learning_rate * cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1)
        return update

    def do_momentum( self, X, Y, update, learning_rate, **kwargs):
        layers = len(self.structure)-1
        grads = self.calculate_grads(X,Y,kwargs["l2_reg_param"])
        for ii in cp.arange(1,layers+1):
            update["w"+str(ii)] = kwargs["gamma"] * update.get("w"+str(ii),0) + learning_rate * cp.sum(grads["w"+str(ii)],axis=0)
            update["b"+str(ii)] = kwargs["gamma"] * update.get("b"+str(ii),0) + learning_rate * cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1)
            self.params["w"+str(ii)] -= update["w"+str(ii)]
            self.params["b"+str(ii)] -= update["b"+str(ii)]
        return update

    def do_nesterov( self, X, Y, update, learning_rate, **kwargs):
        layers = len(self.structure)-1
        for ii in range(1,layers+1):
            self.params["w"+str(ii)] -= kwargs["gamma"] * update.get("w"+str(ii),0)
            self.params["b"+str(ii)] -= kwargs["gamma"] * update.get("b"+str(ii),0)
        grads = self.calculate_grads(X,Y,kwargs["l2_reg_param"])
        for ii in cp.arange(1,layers+1):
            update["w"+str(ii)] = kwargs["gamma"] * update.get("w"+str(ii),0) + learning_rate * cp.sum(grads["w"+str(ii)],axis=0)
            update["b"+str(ii)] = kwargs["gamma"] * update.get("b"+str(ii),0) + learning_rate * cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1)
            self.params["w"+str(ii)] -= update["w"+str(ii)]
            self.params["b"+str(ii)] -= update["b"+str(ii)]
        return update

    def do_rmsprop( self, X, Y, update, learning_rate, **kwargs):
        layers = len(self.structure)-1
        grads = self.calculate_grads(X,Y,kwargs["l2_reg_param"])
        for ii in cp.arange(1,layers+1):
            update["w"+str(ii)] = kwargs["beta"]*update.get("w"+str(ii),0) + (1-kwargs["beta"])*cp.square(cp.sum(grads["w"+str(ii)],axis=0))
            update["b"+str(ii)] = kwargs["beta"]*update.get("b"+str(ii),0) + (1-kwargs["beta"])*cp.square(cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1))
            self.params["w"+str(ii)] -= cp.multiply((learning_rate/ cp.sqrt(kwargs["epsilon"] + update["w"+str(ii)])),\
                                                    cp.sum(grads["w"+str(ii)],axis=0))
            self.params["b"+str(ii)] -= cp.multiply((learning_rate / cp.sqrt(kwargs["epsilon"] + update["b"+str(ii)])),\
                                                    cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1))
        return update

    def do_adam( self, X, Y, update, learning_rate, **kwargs):
        layers = len(self.structure)-1
        grads = self.calculate_grads(X,Y,kwargs["l2_reg_param"])
        for ii in cp.arange(1,layers+1):
            update["mw"+str(ii)] = kwargs["beta1"]*update.get("mw"+str(ii),0) + (1-kwargs["beta1"])*cp.sum(grads["w"+str(ii)],axis=0)
            update["mb"+str(ii)] = kwargs["beta1"]*update.get("mb"+str(ii),0) + (1-kwargs["beta1"])*cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1)
            update["vw"+str(ii)] = kwargs["beta2"]*update.get("vw"+str(ii),0) + (1-kwargs["beta2"])*cp.square(cp.sum(grads["w"+str(ii)],axis=0))
            update["vb"+str(ii)] = kwargs["beta2"]*update.get("vb"+str(ii),0) + (1-kwargs["beta2"])*cp.square(cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1))
            self.params["w"+str(ii)] -= cp.multiply((learning_rate/cp.sqrt(kwargs["epsilon"] + (update["vw"+str(ii)]/(1-kwargs["beta2"]**kwargs["step_num"])))) ,\
                                                    update["mw"+str(ii)]/(1-kwargs["beta1"]**kwargs["step_num"]))
            self.params["b"+str(ii)] -= cp.multiply((learning_rate/cp.sqrt(kwargs["epsilon"] + (update["vb"+str(ii)]/(1-kwargs["beta2"]**kwargs["step_num"])))) ,\
                                                    update["mb"+str(ii)]/(1-kwargs["beta1"]**kwargs["step_num"]))
        return update
    
    def do_nadam( self, X, Y, update, learning_rate, **kwargs):
        layers = len(self.structure)-1
        grads = self.calculate_grads(X,Y,kwargs["l2_reg_param"])
        for ii in cp.arange(1,layers+1):
            update["mw"+str(ii)] = kwargs["beta1"]*update.get("mw"+str(ii),0) + (1-kwargs["beta1"])*cp.sum(grads["w"+str(ii)],axis=0)
            update["mb"+str(ii)] = kwargs["beta1"]*update.get("mb"+str(ii),0) + (1-kwargs["beta1"])*cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1)
            update["vw"+str(ii)] = kwargs["beta2"]*update.get("vw"+str(ii),0) + (1-kwargs["beta2"])*cp.square(cp.sum(grads["w"+str(ii)],axis=0))
            update["vb"+str(ii)] = kwargs["beta2"]*update.get("vb"+str(ii),0) + (1-kwargs["beta2"])*cp.square(cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1))
            self.params["w"+str(ii)] -= cp.multiply( (learning_rate / cp.sqrt(kwargs["epsilon"] + (update["vw"+str(ii)]/(1-kwargs["beta2"]**kwargs["step_num"])))),\
                                        kwargs["beta1"]*(update["mw"+str(ii)]/(1-kwargs["beta1"]**kwargs["step_num"]) +\
                                        ((1-kwargs["beta1"])/(1-kwargs["beta1"]**kwargs["step_num"]))*cp.sum(grads["w"+str(ii)],axis=0) ))
            self.params["b"+str(ii)] -= cp.multiply( (learning_rate / cp.sqrt(kwargs["epsilon"] + (update["vb"+str(ii)]/(1-kwargs["beta2"]**kwargs["step_num"])))),\
                                        kwargs["beta1"]*(update["mb"+str(ii)]/(1-kwargs["beta1"]**kwargs["step_num"]) +\
                                        ((1-kwargs["beta1"])/(1-kwargs["beta1"]**kwargs["step_num"]))*cp.sum(grads["b"+str(ii)],axis=1).reshape(-1,1) ))
        return update

    def get_loss(self,X,Y,l2_reg_param=0,Y_pred=None):
        weight_sum=0
        for ii in range(1,len(self.structure)):
            weight_sum += cp.sum(cp.square(self.params["w"+str(ii)]))
        if Y_pred is None:
            Y_pred = self.predict(X)
        return cp.asnumpy((cp.sum(-cp.log(cp.choose(Y,Y_pred))) + (l2_reg_param/2)*weight_sum) / len(Y))
        

    def do_back_prop(self,X,Y,X_cv,Y_cv,optimiser,gamma,numepochs,learning_rate,batch_size,beta,epsilon,beta1,beta2,l2_reg_param):
        layers = len(self.structure)-1
        update = {}
        step_count = 0
        for i in range(numepochs):
            X_cpu = cp.asnumpy(X)
            Y_cpu = cp.asnumpy(Y)
            wandb.log({"Sample Data":[wandb.Image(X_cpu[:,jj].reshape(28,28),caption=dataset_labels[Y_cpu[jj]])\
                                      for jj in range(20*i,20*i+20)]},commit = False)
            for j in tqdm(range(math.ceil(X.shape[1]/batch_size))):
                X_pass = X[:,j*batch_size:min(X.shape[1],(j+1)*batch_size)]
                Y_pass = Y[j*batch_size:min(X.shape[1],(j+1)*batch_size)]
                step_count += 1
                update = (self.optimisers[optimiser])( X_pass, Y_pass, update, learning_rate, gamma = gamma, beta = beta,\
                        beta1 = beta1, beta2 = beta2, epsilon = epsilon, l2_reg_param = l2_reg_param, step_num = step_count)
                Y_pred = self.predict(X)
                self.accuracies.append(cp.asnumpy(cp.mean(cp.argmax(Y_pred,axis=0)==Y)))
                self.cvaccuracies.append(cp.asnumpy(cp.mean(self.predict(X_cv,returnclass=1)==Y_cv)))
                self.losses.append(self.get_loss(None,Y,l2_reg_param,Y_pred))
                self.cvlosses.append(self.get_loss(X_cv,Y_cv,l2_reg_param))
                wandb.log({"train_acc":self.accuracies[-1],"train_loss":self.losses[-1],"val_acc":self.cvaccuracies[-1],\
                           "val_loss":self.cvlosses[-1],"step_count":step_count})


    def train(self,X,Y,numepochs = 100,learning_rate = 0.1,initialization_type = "random",activation = "sigmoid",\
              optimiser = "sgd",gamma=0.1,init_params=True,train_test_split=0.2,seed=None,batch_size = 32,beta=0.99,\
              epsilon=0.0000001,beta1=0.9,beta2=0.999,l2_reg_param=0):
        if init_params == False and self.params == {}:
            raise(UnboundLocalError("Weights and Biases not initialized. Set init_params to True."))
        if init_params == True:
            self.initialise_params(initialization_type)
            self.activation = activation
        permutation = cp.arange(X.shape[1])
        cp.random.seed(seed)
        cp.random.shuffle(permutation)
        X = ((X.T)[permutation]).T
        Y = Y[permutation]
        X_cv = X[:,:int(X.shape[1]*train_test_split)]
        Y_cv = Y[:int(X.shape[1]*train_test_split)]
        temp = X.shape[1]
        X = X[:,int(temp*train_test_split):] 
        Y = Y[int(temp*train_test_split):]
        self.accuracies = []
        self.cvaccuracies = []
        self.losses = []
        self.cvlosses = []
        self.do_back_prop(X,Y,X_cv,Y_cv,optimiser,gamma,numepochs,learning_rate,batch_size,beta,epsilon,beta1,beta2,l2_reg_param)

    
    def predict(self,X,returndict = 0,returnclass = 0):
        predictions = X
        if returndict == 1:
            values = {}
            values["h0"] = X
        layers = len(self.structure)-1
        for i in range(layers-1):
            predictions = cp.matmul( self.params["w"+str(i+1)], predictions) + self.params["b"+str(i+1)]
            if returndict == 1:    
                values["a"+str(i+1)]=predictions
            predictions = NeuralNet.activate(predictions,self.activation)
            if returndict == 1:
                values["h"+str(i+1)]=predictions
        predictions = cp.matmul( self.params["w"+str(layers)], predictions) + self.params["b"+str(layers)]
        if returndict == 1:
            values["a"+str(layers)]=predictions
        if returnclass == 1:
            return cp.argmax(predictions,axis=0)
        cp.clip(predictions,-700,700)
        predictions = cp.exp(predictions)/cp.sum(cp.exp(predictions),axis=0)
        if returndict == 1:
            values["h"+str(layers)]=predictions
        if returndict ==0:
            return predictions
        else:
            return values
            
# %%
(X_train_cpu,Y_train_cpu),(X_test_cpu,Y_test_cpu) = fashion_mnist.load_data()
X_train = cp.asarray(X_train_cpu)
Y_train = cp.asarray(Y_train_cpu)
X_test = cp.asarray(X_test_cpu)
Y_test = cp.asarray(Y_test_cpu)

X_train = X_train.reshape(X_train.shape[0],-1).T/256
X_test = X_test.reshape(X_test.shape[0],-1).T/256



# %%

# %%
dataset_labels = { 0:"T-shirt/top", 1:"Trouser/pants", 2:"Pullover shirt", 3:"Dress", 4:"Coat",\
                5:"Sandal", 6:"Shirt", 7:"Sneaker", 8:"Bag", 9:"Ankle boot"}

# %%
nn = NeuralNet(wandb.config["input_size"],wandb.config["output_size"])
nn.addlayer(wandb.config["hidden_1"])
nn.addlayer(wandb.config["hidden_2"])
nn.addlayer(wandb.config["hidden_3"])
if wandb.config["hidden_4"] != 0 and wandb.config["hidden_5"] != 0:
    nn.addlayer(wandb.config["hidden_4"])
    nn.addlayer(wandb.config["hidden_5"])
elif wandb.config["hidden_4"] != 0 and wandb.config["hidden_5"] == 0:
    nn.addlayer(wandb.config["hidden_4"])
elif wandb.config["hidden_4"] == 0 and wandb.config["hidden_5"] == 0:
    pass
else:
    current_wandb_run.finish()

nn.train(X_train,Y_train,wandb.config["epochs"],wandb.config["learning_rate"],\
         initialization_type=wandb.config["initialization_type"],activation=wandb.config["activation"],optimiser=wandb.config["optimiser"],\
         gamma=wandb.config["gamma"],batch_size=wandb.config["batch_size"],train_test_split=wandb.config["train_test_split"],seed=wandb.config["seed"],\
         beta=wandb.config["beta"],epsilon=wandb.config["epsilon"],beta1=wandb.config["beta1"],beta2=wandb.config["beta2"],\
         l2_reg_param=wandb.config["l2_reg_param"],init_params=wandb.config["init_params"])
current_wandb_run.finish()

# %%

# %%
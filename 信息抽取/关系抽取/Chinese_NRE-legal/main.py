import time
import sys
import argparse
import random
import copy
import torch
import gc
import torch.autograd as autograd
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import re
import sklearn.metrics
from nn.framework import MGLattice_model
from utils.data import Data
from utils.data_manager import *
from utils.metric import *
import configure
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.append("..")

import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"
sys.setrecursionlimit(2000000)
import torch._utils
try:
    torch._utils._rebuild_tensor_v2
except AttributeError:
    def _rebuild_tensor_v2(storage, storage_offset, size, stride, requires_grad, backward_hooks):
        tensor = torch._utils._rebuild_tensor(storage, storage_offset, size, stride)
        tensor.requires_grad = requires_grad
        tensor._backward_hooks = backward_hooks
        return tensor
    torch._utils._rebuild_tensor_v2 = _rebuild_tensor_v2

def evaluate_forward(data, model, name):
        
    model.eval()
    batch_size = 1
    start_time = time.time()
    y_ans = []
    y_pred = []
    for batch in data.batch_iter(name,batch_size,False):
        
        gaz_list, batch_word, batch_biword, batch_wordlen, batch_char, batch_charlen, batch_charrecover, batch_pos1, batch_pos2, ins_label, batch_label, mask, scope,ent1,ent2 = batch
        prob = model(gaz_list, batch_word, batch_biword, batch_wordlen, batch_char, batch_charlen, batch_charrecover, batch_pos1, batch_pos2, ins_label, scope)
        
        prob = prob.cpu().data.numpy()
        assert batch_size == len(batch_label)
        
        for bid in range(batch_size):
            cur_ans = batch_label[bid]
            cur_ans = list(set(cur_ans))  #真实的标签
            
            cur_prob = prob[bid] #预测的标签
            
            y_ans.append(cur_ans)
            y_pred.append(cur_prob)
        
    return y_ans,y_pred #,(ent1,ent2)   
    
'''
return precision, recall, accuracy, f1
'''
def evaluate(data, model, name): 
    y_ans,y_pred = evaluate_forward(data,model,name)
    return calc_evaluation(y_ans, y_pred)

def load_eval(data, model_dir, name):
    data.HP_gpu = torch.cuda.is_available()
    print('Load model from ', model_dir)
    model = nn.DataParallel(MGLattice_model(data))   
    model.load_state_dict(torch.load(model_dir))
    if data.HP_gpu:
        model = model.cuda()

    start_time = time.time()
    y_ans,y_pred = evaluate_forward(data, model, name)
        
    precision, recall, f1, auc = calc_evaluation(y_ans,y_pred)
    
    end_time = time.time()
    time_cost = end_time - start_time
    print("Finish testing")
    print("Test: time: %.2fs; f1: %.4f; auc: %.4f"%(time_cost, f1, auc))
    
def my_load_eval(data, model_dir, name):
    data.HP_gpu = torch.cuda.is_available()
    print('Load model from ', model_dir)
    model = nn.DataParallel(MGLattice_model(data))   
    model.load_state_dict(torch.load(model_dir))
    if data.HP_gpu:
        model = model.cuda()
    #print(len(data.test_texts))
    start_time = time.time()
    y_ans,y_pred = evaluate_forward(data, model, name)
    #print(y_ans,y_pred)    
    precision, recall, f1, auc = calc_evaluation(y_ans,y_pred)
    
    end_time = time.time()
    time_cost = end_time - start_time
    print("Finish testing")
    print("Test: time: %.2fs; p: %.4f; r: %.4f; f1: %.4f; auc: %.4f"%(time_cost, precision, recall, f1, auc))
    
# Set decay of learning rate
def lr_decay(optimizer, epoch, decay_rate, init_lr):
    lr = init_lr * ((1-decay_rate)**epoch)
    print(" Learning rate is setted as:", lr)
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
    return optimizer


def draw_curve(data, xlabel, ylabel, outputfile):
       
    plt.figure()
    plt.xticks(fontsize=10)
    plt.yticks(fontsize=10)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.plot(data)
    plt.savefig(outputfile)

# Train the model
def train(data, save_model_dir):
    data.show_data_summary()
    save_data_name = save_model_dir + '.dset'
    save_data_setting(data, save_data_name)
    # initialize the model
    model = nn.DataParallel(MGLattice_model(data))
    # use GPU
    if data.HP_gpu:
        model = model.cuda()

    parameters = filter(lambda p: p.requires_grad, model.parameters())
    if configure.Optimizer == 'Adam':
        optimizer = optim.Adam(parameters, lr = data.HP_lr)
    elif configure.Optimizer == 'SGD':
        optimizer = optim.SGD(parameters, lr = data.HP_lr, momentum=data.HP_momentum)
    else:
        print("Error: the configure of Optimizer is illegal:%s"%(configure.Optimizer))
    total_loss = 0

    best_f1 = -1
    best_auc = -1

    weight = data.weights
    if weight is None:
        loss_fn = torch.nn.CrossEntropyLoss()
    else:
        weight = torch.cuda.FloatTensor(weight)
        loss_fn = torch.nn.CrossEntropyLoss(weight=weight)
        
    training_step_loss_history = []
    training_loss_history = []

    for idx in range(data.HP_iteration):
        
        accumulated_train_loss = 0
        epoch_start = time.time()
        temp_start = epoch_start
        print("Epoch: %s/%s" %(idx,data.HP_iteration))
        if configure.Optimizer == 'SGD':
            optimizer = lr_decay(optimizer, idx, data.HP_lr_decay, data.HP_lr)
        
        model.train()
        model.zero_grad()
        batch_size = 2
        batch_loss = 0
        batch_num=0
        
        for batch in data.batch_iter('train',batch_size):
            
            gaz_list, batch_word, batch_biword, batch_wordlen, batch_char, batch_charlen, batch_charrecover, batch_pos1, batch_pos2, ins_label, batch_label, mask, scope ,_,_= batch
            prob = model(gaz_list, batch_word, batch_biword, batch_wordlen, batch_char, batch_charlen, batch_charrecover, batch_pos1, batch_pos2, ins_label, scope) # batch_size*num_classes
            #print(prob.shape,batch_label.shape,batch_word.shape)
            #print(batch_label)
            print(prob,batch_label)
            batch_loss = loss_fn(prob, batch_label)
            print(batch_loss)
            step_loss= batch_loss.data.cpu().numpy()
            #training_step_loss_history.append(step_loss)
            accumulated_train_loss += step_loss

            #print(prob.shape,batch_label.shape)
            batch_loss.backward()
            optimizer.step()
            model.zero_grad()
            batch_loss = 0
       
        temp_time = time.time()
        temp_cost = temp_time - temp_start
        # print('accumulate loss:',accumulated_train_loss)
        train_loss = accumulated_train_loss / batch_size
        # print(train_loss)
        training_step_loss_history.append(train_loss)
        
        epoch_finish = time.time()
        epoch_cost = epoch_finish - epoch_start
        print("Epoch: %s training finished. Time: %.2fs"%(idx, epoch_cost))

        # Validation
        precision, recall, f1, auc = evaluate(data, model, 'dev')
        dev_finish = time.time()
        dev_cost = dev_finish - epoch_finish
        print("Dev: time: %.2fs; f1: %.4f; auc: %.4f"%(dev_cost, f1, auc))
        if auc > best_auc:
            print('Current auc ',auc,'exceed previous best auc:',best_auc)
            if f1 <= best_f1:   #如果只有准确率高了也保存模型
                model_name = save_model_dir #+ '_' + '{:.4g}_{:.4g}'.format(100.0*f1,100.0*auc) + '-' +str(idx)
                torch.save(model.state_dict(), model_name)
            best_auc = auc

        if f1 > best_f1:    #如果只有f值高了也保存模型
            print('Current f1 ',f1,'exceed previous best f1:',best_f1)
            model_name = save_model_dir# + '_' + '{:.4g}_{:.4g}'.format(100.0*f1,100.0*auc) + '-' +str(idx)
            torch.save(model.state_dict(), model_name)
            best_f1 = f1

        # Testing
        precision, recall, f1, auc = evaluate(data, model, 'test')
        test_finish = time.time()
        test_cost = test_finish - dev_finish
        print("Test: time: %.2fs; p: %.4f; r: %.4f; f1: %.4f; auc: %.4f"%(test_cost, precision, recall, f1, auc))
        print("============================================================")
    draw_curve(training_step_loss_history, 'Steps', 'Training Error', '_train_step_curve.png')
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Tuning')
    parser.add_argument('--status', choices=['train', 'test'], help='update algorithm', default='train')
    args = parser.parse_args()
    status = args.status
    #draw_curve([1,2,4,6,7,9], 'Steps', 'Training Error', '_train_step_curve.png')
    # load all corresponding data
    data = load_data(status)
    print(data.char_alphabet)
    print(data.word_alphabet)
    #data=load_data_setting(configure.trsaveset)
    #print('trainid',data.train_Ids)
    if status == 'train':
        print("Model saved to:", configure.savedset)
        print('Ready for training.')
        train(data, configure.savemodel)

    elif status == 'test':
        print('Ready for testing.')
        my_load_eval(data, configure.loadmodel, 'test')



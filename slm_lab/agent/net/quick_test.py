import torch
import torch.nn as nn
from torch import optim
from convnet import ConvNet
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable

dummy_input = Variable(torch.ones((2, 3, 32, 32)))
net = ConvNet((3, 32, 32),
         [[3, 16, (5, 5), 2, 0, 1],
             [16, 32, (5, 5), 2, 0, 1]],
         [100, 50],
         10,
         optim.Adam,
         F.smooth_l1_loss,
         False,
         False)

print(net)
out = net(dummy_input)

net = ConvNet((3, 32, 32),
         [[3, 16, (5, 5), 2, 0, 1],
             [16, 32, (5, 5), 2, 0, 1]],
         [100, 50],
         10,
         optim.Adam,
         F.smooth_l1_loss,
         False,
         True)

print(net)
out = net(dummy_input)

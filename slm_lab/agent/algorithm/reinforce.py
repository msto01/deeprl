from slm_lab.agent import memory
from slm_lab.agent import net
from slm_lab.agent.algorithm.algorithm_util import act_fns, act_update_fns
from slm_lab.agent.algorithm.base import Algorithm
from slm_lab.agent.net import net_util
from slm_lab.lib import logger, util
from torch.autograd import Variable
import numpy as np
import torch
import pydash as _


class ReinforceDiscrete(Algorithm):
    '''
    TODO
    Adapted from https://github.com/pytorch/examples/blob/master/reinforcement_learning/reinforce.py
    '''

    def __init__(self, agent):
        super(ReinforceDiscrete, self).__init__(agent)
        self.agent = agent

    def post_body_init(self):
        '''Initializes the part of algorithm needing a body to exist first.'''
        body = self.agent.flat_nonan_body_a[0]  # singleton algo
        state_dim = body.state_dim
        action_dim = body.action_dim
        net_spec = self.agent.spec['net']
        self.net = getattr(net, net_spec['type'])(
            state_dim, net_spec['hid_layers'], action_dim,
            hid_layers_activation=_.get(net_spec, 'hid_layers_activation'),
            optim_param=_.get(net_spec, 'optim'),
            loss_param=_.get(net_spec, 'loss'),
            clamp_grad=_.get(net_spec, 'clamp_grad'),
            clamp_grad_val=_.get(net_spec, 'clamp_grad_val'),
        )
        print(self.net)
        algorithm_spec = self.agent.spec['algorithm']
        self.action_policy = act_fns[algorithm_spec['action_policy']]
        self.num_epis = algorithm_spec['num_epis_to_collect']
        self.gamma = algorithm_spec['gamma']
        # To save on a forward pass keep the log probs from each action
        self.saved_log_probs = []
        self.to_train = 0

    def body_act_discrete(self, body, state):
        return self.action_policy(self, state, self.net)

    def sample(self):
        '''Samples a batch from memory'''
        batches = [body.memory.sample()
                   for body in self.agent.flat_nonan_body_a]
        batch = util.concat_dict(batches)
        batch = util.to_torch_nested_batch(batch)
        return batch

    def train(self):
        # logger.debug(f'Train? {self.to_train}')
        if self.to_train == 1:
            # Only care about the rewards
            rewards = self.sample()['rewards']
            logger.debug(f'Length first epi: {len(rewards[0])}')
            advantage = self.calculate_advantage(rewards)
            logger.debug(f'Len log probs: {len(self.saved_log_probs)}')
            logger.debug(f'Len advantage: {advantage.size(0)}')
            assert len(self.saved_log_probs) == advantage.size(0)
            policy_loss = []
            for log_prob, a in zip(self.saved_log_probs, advantage):
                policy_loss.append(-log_prob * a)
            self.net.optim.zero_grad()
            policy_loss = torch.cat(policy_loss).sum()
            loss = policy_loss.data[0]
            policy_loss.backward()
            if self.net.clamp_grad:
                logger.info("Clipping gradient...")
                torch.nn.utils.clip_grad_norm(
                    self.net.parameters(), self.net.clamp_grad_val)
            logger.debug(f'Gradient norms: {self.net.get_grad_norms()}')
            self.net.optim.step()
            self.to_train = 0
            self.saved_log_probs = []
            logger.debug(f'Policy loss: {loss}')
            return loss
        else:
            return None

    def calculate_advantage(self, raw_rewards):
        advantage = []
        logger.debug(f'Raw rewards: {raw_rewards}')
        for epi_rewards in raw_rewards:
            rewards = []
            R = 0
            for r in epi_rewards[::-1]:
                R = r + self.gamma * R
                rewards.insert(0, R)
            rewards = torch.Tensor(rewards)
            logger.debug(f'Rewards: {rewards}')
            rewards = (rewards - rewards.mean()) / \
                (rewards.std() + np.finfo(np.float32).eps)
            logger.debug(f'Normalized rewards: {rewards}')
            advantage.append(rewards)
        advantage = torch.cat(advantage)
        return advantage

    def update(self):
        '''No update needed'''
        # TODO: fix return value when no explore var
        return 1

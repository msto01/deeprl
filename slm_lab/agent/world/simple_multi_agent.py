import copy
import os
import random
from copy import deepcopy

import numpy as np
import torch

from slm_lab.agent.agent.agent import Agent, Body
from slm_lab.experiment import analysis
from slm_lab.lib import logger, util, viz
from slm_lab.lib.decorator import lab_api

logger = logger.get_logger(__name__)

import torch.cuda
from torch._C import default_generator

class DefaultMultiAgentWorld:
    '''
    World abstraction; implements the API to interface with Env in SLM Lab
    Contains algorithm(s), memory(s), body(s), agent(s)

    world < env
        + agents < algorithm + memory + body + welfare_function

    '''

    def __init__(self, spec, env, global_nets_list=None):

        self.spec = spec

        util.set_attr(self, dict(
            deterministic=False,
        ))
        util.set_attr(self, self.spec["world"], [
            'deterministic',
        ])

        self.agents = []
        self.env = env
        self.best_total_rewards_ma = -np.inf
        self.session_idx = None  # Will be set in the Session __init__
        self.trial_idx = None

        # TODO rename deterministic (use to apply the same rd number to all agents)
        if self.deterministic:
            self.rd_seed = np.random.randint(1e9)
        for i, agent_spec in enumerate(deepcopy(spec['agent'])):
            if self.deterministic:
                self._set_rd_state(self.rd_seed)
            self._create_one_agent(i, agent_spec, global_nets_list[i]
                if global_nets_list is not None else None)

        self.body = Body(self.env, self.spec, agent=None)

        if self.deterministic:
            if torch.cuda.is_available():
                torch.backends.cudnn.benchmark = False
                torch.backends.cudnn.deterministic = True

        self.playing_agents = [ag.playing_agent for ag in self.agents]

    def _create_one_agent(self, agent_idx, agent_spec, global_nets):
        a_spec = deepcopy(self.spec)
        a_spec.update({'agent': agent_spec, 'name': agent_spec['name']})
        self.agents.append(Agent(spec=a_spec, env=self.env, global_nets=global_nets,
                                 agent_idx=agent_idx, world=self))

    @property
    def bodies(self):
        return [a.body for a in self.agents]

    @property
    def total_rewards_ma(self):
        return sum([body.total_reward_ma for body in self.bodies])

    @property
    def algorithms(self):
        return [a.algorithm for a in self.agents]

    @property
    def name(self):
        return str([a.name for a in self.agents])

    @lab_api
    def act(self, state):
        '''Standard act method from algorithm.'''

        action_action_pd = [agent.act(s) for agent, s in zip(self.agents, state) if agent.playing_agent]
        action = [el[0] for el in action_action_pd]
        action_pd = [el[1] for el in action_action_pd]
        return action, action_pd

    @lab_api
    def update(self, state, action, reward, next_state, done):
        '''Update per timestep after env transitions, e.g. memory, algorithm, update agent params, train net'''
        logger.debug(f'action {action}')

        assert sum(self.playing_agents) == len(state) == len(action) == len(reward) == len(next_state), (
            f"playing {sum(self.playing_agents)} s {len(state)} a {len(action)} "
            f"r {len(reward)} n_s {len(next_state)}"
        )

        reward, next_state = self._update_agent_info_wt_feedback_from_env_step(reward, next_state, done)
        loss, explore_var = [], []

        # Update memory and make it work with non-playing agents as well
        playing_pos = 0
        for idx, (agent, playing) in enumerate(zip(self.agents, self.playing_agents)):
            if playing:
                agent.update(state[playing_pos], action[playing_pos], reward[playing_pos],
                             next_state[playing_pos], done)
                playing_pos += 1
            else:
                agent.update(None, None, None, None, done)

        # Train supporting determinisctic similar seed for all agent
        if self.deterministic:
            self.rd_seed = np.random.randint(1e9)
        for agent in self.agents:
            if self.deterministic:
                self._set_rd_state(self.rd_seed)
            l, e_v = agent.train()
            if l is not None:
                loss.append(torch.tensor([l]))
            if e_v is not None:
                explore_var.append(torch.tensor([e_v]))

        if not any([np.isnan(l) for l in loss]):  # set for log_summary()
            sum_loss_over_agents = torch.cat(loss, dim=0).sum()
            # sum_explore_var_over_agents = torch.cat(explore_var, dim=0).sum()
            # self.body.loss = sum_loss_over_agents
            # self.body.explore_var = sum_explore_var_over_agents
            if util.in_eval_lab_modes():
                # return sum_loss_over_agents, sum_explore_var_over_agents
                return sum_loss_over_agents, None

    def _update_agent_info_wt_feedback_from_env_step(self, reward, next_state, done):

        self.reward = reward
        self.next_state = next_state

        self._complement_agent_information_about_step(reward, next_state, done)

        something_changed = False
        for agent in self.agents:
            if hasattr(agent, "act_after_env_step"):
                with torch.no_grad():
                    outputs = agent.act_after_env_step()
                    for k, v in outputs.items():
                        if hasattr(self, k):
                            something_changed = True
                            setattr(self, k, v)

        reward = self.reward
        next_state = self.next_state

        if something_changed:
            self._complement_agent_information_about_step(reward, next_state, done)

        for agent in self.agents:
            agent.compute_welfare()

        return reward, next_state

    def _complement_agent_information_about_step(self, reward, next_state, done):
        playing_pos = 0
        for idx, (agent, playing) in enumerate(zip(self.agents, self.playing_agents)):
            if playing:
                agent.set_step_values(reward[playing_pos], next_state[playing_pos], done)
                playing_pos += 1
            else:
                agent.set_step_values(None, None, done)

    def manual_seed(self,seed):
        """Without memory leak"""
        seed = int(seed)
        # if not torch.cuda._in_bad_fork:
        #     torch.cuda.manual_seed_all(seed)
        default_generator.manual_seed(seed)

    def _set_rd_state(self, seed):
        random.seed(seed)
        np.random.seed(seed)
        self.manual_seed(seed)
        # # torch.cuda.manual_seed(seed)
        # torch.cuda.manual_seed_all(seed)

    @lab_api
    def save(self, ckpt=None):
        '''Save agent'''
        for agent in self.agents:
            agent.save(ckpt=ckpt)

    @lab_api
    def close(self):
        '''Close and cleanup agent at the end of a session, e.g. save model'''
        for agent in self.agents:
            agent.close()

    def ckpt(self, df_mode='train'):
        """
        Executed each n frames during training
        Compute and log metrics
        """
        one_time_print_table = []
        table_train_metrics = []
        table_sessions_metrics = []
        objects_to_analyse = self.agents + [self]
        col_to_print_one_time = ["epi", "t", "wall_t", "frame", "fps"]
        log_session_metrics = False

        for idx, object_to_analyse in enumerate(objects_to_analyse):

            if idx > len(self.agents) - 1:
                train_metrics = {"obj": "world"}
            else:
                train_metrics = {"obj": f"agent_n{idx}"}

            object_to_analyse.body.ckpt(self.env, df_mode)
            train_metrics.update(object_to_analyse.body.log_summary(df_mode))

            # print only one time some columns
            if idx > len(self.agents) - 1:
                one_time_dict = {"trial": self.trial_idx,
                                 "session": self.session_idx}
                for col in col_to_print_one_time:
                    one_time_dict[col] = train_metrics[col]
                one_time_print_table.append(one_time_dict)
            for col in col_to_print_one_time:
                train_metrics.pop(col)
            table_train_metrics.append(train_metrics)

            if len(object_to_analyse.body.train_df) > 2:  # need more rows to calculate metrics
                if not log_session_metrics: log_session_metrics = True
                if idx > len(self.agents) - 1:
                    agent_metrics = {"obj": "world"}
                else:
                    agent_metrics = {"obj": f"agent_n{idx}"}

                spec_temp = copy.deepcopy(object_to_analyse.spec)
                head, tail = os.path.split(spec_temp['meta']['info_prepath'])
                spec_temp['meta']['info_prepath'] = os.path.join(head, f'{train_metrics["obj"]}_' + tail)

                agent_metrics.update(
                    analysis.analyze_session(spec_temp, object_to_analyse.body.train_df,
                                             df_mode, plot=False)['scalar'])
                table_sessions_metrics.append(agent_metrics)

        # Log
        logger.info(f"\n")
        logger.info(f"Training metrics")
        self._print_as_table(one_time_print_table)
        self._print_as_table(table_train_metrics)
        if log_session_metrics:
            logger.info(f"Session metrics")
            self._print_as_table(table_sessions_metrics)

    def _print_as_table(self, my_dict, col_list=None):
        """ Pretty print a list of dictionaries (myDict) as a dynamically sized table.
        If column names (colList) aren't specified, they will show in random order.
        Author: Thierry Husson - Use it as you want but don't blame me.
        """
        if not col_list:
            col_list = []
            if my_dict:
                for one_dict in my_dict:
                    for el in list(one_dict.keys() if my_dict else []):
                        if el not in col_list:
                            col_list.append(el)
        myList = [col_list]  # 1st row = header
        for item in my_dict:
            # myList.append([str(item[col] if item[col] is not None else '') for col in col_list])
            formated_row_values = []
            for col in col_list:
                if col not in item.keys():
                    str_value = ""
                elif item[col] is None:
                    str_value = ""
                elif isinstance(item[col], str):
                    str_value = item[col]
                else:
                    str_value = "{:g}".format(item[col])
                formated_row_values.append(str_value)
            myList.append(formated_row_values)
        colSize = [max(map(len, col)) for col in zip(*myList)]
        formatStr = ' | '.join(["{{:<{}}}".format(i) for i in colSize])
        myList.insert(1, ['-' * i for i in colSize])  # Seperating line
        for item in myList:
            logger.info(formatStr.format(*item))

    def compute_and_log_session_metrics(self, temp_manager=None):
        """
        Executed at the end of each session.
        Compute and log the session metrics for the agents and the overall world.
        """
        # df_mode = 'eval'
        df_modes = ['train', 'eval']
        for df_mode in df_modes:
            session_metrics = {}
            list_metrics = []
            session_metrics_dict = {}
            session_df_dict = {}

            # TODO change this to display a table of metrics
            # Agents metrics
            for agent_idx, agent in enumerate(self.agents):
                agent_session_metrics = analysis.analyze_session(agent.spec, agent.body.eval_df, df_mode)
                if temp_manager is not None:
                    temp_manager()
                self._log_one_object_metrics(agent_session_metrics['scalar'], df_mode)
                session_metrics[f'agent_{agent_idx}'] = agent_session_metrics
                # To log in tables
                m = {'object': f'agent_{agent_idx}', "df_mode": f'{df_mode}'}
                m.update(agent_session_metrics['scalar'])
                list_metrics.append(m)

                session_metrics_dict[f'agent_n{agent_idx}'] = agent_session_metrics
                session_df_dict[f'agent_n{agent_idx}'] = agent.body.eval_df

            # World metrics
            if len(self.agents) > 1:
                world_session_metrics = analysis.analyze_session(self.spec, self.body.eval_df, df_mode)
                if temp_manager is not None:
                    temp_manager()
                self._log_one_object_metrics(world_session_metrics['scalar'], df_mode)
                session_metrics['world'] = world_session_metrics
                # To log in tables
                m = {'object': 'world', "df_mode": f'{df_mode}'}
                m.update(world_session_metrics['scalar'])
                list_metrics.append(m)

                session_metrics_dict['world'] = world_session_metrics
                session_df_dict['world'] = self.body.eval_df

            self._print_as_table(my_dict=list_metrics)

            # plot graph
            viz.plot_session(self.agents[0].spec, session_metrics_dict,
                             session_df_dict, df_mode)
            if temp_manager is not None:
                temp_manager()
            viz.plot_session(self.agents[0].spec, session_metrics_dict,
                             session_df_dict, df_mode, ma=True)

        return session_metrics

    def _log_one_object_metrics(self, metrics, df_mode):
        '''Log session metrics'''
        # TODO add again prefix since it is useful at the end of session
        # prefix = self.get_log_prefix()
        row_str = '  '.join([f'{k}: {v:g}' for k, v in metrics.items()])
        # msg = f'{prefix} [{df_mode}_df metrics] {row_str}'
        msg = f'[{df_mode} metrics] {row_str}'
        logger.info(msg)

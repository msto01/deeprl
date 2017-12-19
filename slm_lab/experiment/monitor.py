'''
The monitor module with data_space
Monitors agents, environments, sessions, trials, experiments, evolutions, and handles all the data produced by the Lab components.
InfoSpace handles the unified hyperdimensional data for SLM Lab, used for analysis and experiment planning. Sources data from monitor.
Each dataframe resolves from the coarsest dimension to the finest, with data coordinates coor in the form: (evolution,experiment,trial,session,agent,env,body)
The resolution after session is the AEB space, hence it is a subspace.
AEB space is not necessarily tabular, and hence the data is NoSQL.

The data_space is congruent to the coor, with proper resolution.
E.g. (evolution,experiment,trial,session) specifies the session_data of a session, ran over multiple episodes on the AEB space.

Space ordering:
InfoSpace: the general space for complete information
AEBSpace: subspace of InfoSpace for a specific session
AgentSpace: space agent instances, subspace of AEBSpace
EnvSpace: space of env instances, subspace of AEBSpace
DataSpace: a data space storing an AEB data projected to a-axis, and its dual projected to e-axis. This is so that a-proj data like action_space from agent_space can be used by env_space, which requires e-proj data, and vice versa.

Object reference (for agent to access env properties, vice versa):
Agents - AgentSpace - AEBSpace - EnvSpace - Envs
'''
# TODO - plug to NoSQL graph db, using graphql notation, and data backup
# TODO - data_space viewer and stats method for evaluating and planning experiments
from copy import deepcopy
from slm_lab.lib import logger, util
from slm_lab.spec import spec_util
import numpy as np
import pandas as pd
import pydash as _

# These correspond to the control unit classes, lower cased
COOR_AXES = [
    'evolution',
    'experiment',
    'trial',
    'session',
]
COOR_AXES_ORDER = {
    axis: idx for idx, axis in enumerate(COOR_AXES)
}
COOR_DIM = len(COOR_AXES)
AGENT_DATA_NAMES = ['action']
ENV_DATA_NAMES = ['state', 'reward', 'done']


def get_body_df_dict(aeb_space):
    body_df_dict = {}
    reward_proj_h = []
    done_proj_h = []
    for a, body_proj_a in enumerate(aeb_space.body_space.data_proj):
        reward_proj_a_t = np.column_stack(
            [reward_proj_t[a] for reward_proj_t in aeb_space.data_spaces['reward'].data_proj_history])
        done_proj_a_t = np.column_stack(
            [done_proj_t[a] for done_proj_t in aeb_space.data_spaces['done'].data_proj_history])
        reward_proj_h.append(reward_proj_a_t)
        done_proj_h.append(done_proj_a_t)
        for a_idx, body in enumerate(body_proj_a):
            body.reward_h = reward_proj_a_t[a_idx]
            body.done_h = done_proj_a_t[a_idx]
            df = pd.DataFrame({'reward': body.reward_h, 'done': body.done_h})
            # df['e'] = df['done'].cumsum()
            # e_df = df[['reward']].group_by('e').agg('sum')
            body_df_dict[body.aeb] = df
    return body_df_dict


class Clock:
    def __init__(self):
        self.t = 0
        self.total_t = 0
        self.e = 0

    def tick(self, unit='t'):
        if unit == 't':  # timestep
            self.t += 1
            self.total_t += 1
        elif unit == 'e':  # episode, reset timestep
            self.t = 0
            self.e += 1
        else:
            raise KeyError

    def get(self, unit='t'):
        return getattr(self, unit)


class Body:
    '''
    Body, helpful info reference unit under AEBSpace for sharing info between agent and env.
    '''

    def __init__(self, aeb, agent, env):
        self.aeb = aeb
        self.a, self.e, self.b = aeb
        self.clock = Clock()
        self.agent = agent
        self.env = env
        self.observable_dim = self.env.get_observable_dim(self.a)
        # TODO use tuples for state_dim for pixel-based in the future, generalize all and call as shape
        self.state_dim = self.observable_dim['state']
        self.action_dim = self.env.get_action_dim(self.a)
        self.is_discrete = self.env.is_discrete(self.a)

    def __str__(self):
        return 'body: ' + util.to_json(util.get_class_attr(self))


class DataSpace:
    '''
    AEB data space. Store all data from RL system in standard aeb-shaped tensors.
    '''

    def __init__(self, data_name, aeb_space):
        self.data_name = data_name
        self.aeb_space = aeb_space
        self.aeb_shape = aeb_space.aeb_shape

        # data from env have shape (eab), need to transpose
        self.to_transpose = self.data_name in ENV_DATA_NAMES

        self.data = None  # standard data in aeb shape
        self.t_data = None
        # TODO shove history to DB
        # TODO keep time/episode data too, will be cheap
        self.data_history = []  # index = clock.absolute_t

    def __str__(self):
        return str(self.data)

    def __bool__(self):
        return bool(np.all(self.data))

    def add(self, data):
        '''
        Take raw data from RL system and construct numpy object self.data, then add to self.data_history.
        Extend data to rectangular shape padded with nan template, then turn it into numpy tensor. If data is from env, auto-transpose the data to aeb standard shape.
        @param {[x: [y: [body_data]]} data As collected in RL sytem.
        @returns {array} data Tensor in standard aeb shape.
        '''
        body_num = self.aeb_shape[2]  # b of aeb
        for _x, x_list in enumerate(data):
            for y, y_list in enumerate(x_list):
                pad_len = body_num - len(y_list)
                y_list.extend([np.nan] * pad_len)
        new_data = np.array(data)  # no type restriction, auto-infer
        if self.to_transpose:  # data from env has shape eab
            self.data = new_data.T
            self.t_data = new_data
        else:
            self.data = new_data
            self.t_data = new_data.T
        self.data_history.append(self.data)
        return self.data

    def get(self, a=None, e=None):
        '''
        Get the data projected on a or e axes for use by agent_space, env_space.
        @param {int} a The index a of an agent in agent_space
        @param {int} e The index e of an env in env_space
        @returns {array} data_x Where x is a or e.
        '''
        if e is None:
            return self.data[a]
        else:
            return self.t_data[e]


class AEBSpace:

    def __init__(self, spec):
        # TODO shove
        # self.info_space = info_space
        self.spec = spec
        self.clock = Clock()
        self.agent_space = None
        self.env_space = None
        self.body_space = None
        (self.aeb_list, self.aeb_shape, self.aeb_sig) = self.get_aeb_info(self.spec)
        self.data_spaces = self.init_data_spaces()

    def get_aeb_info(cls, spec):
        '''
        Get from spec the aeb_list, aeb_shape and aeb_sig, which are used to resolve agent_space and env_space.
        @returns {list, (a,e,b), array([a, e, b])} aeb_list, aeb_shape, aeb_sig
        '''
        aeb_list = spec_util.resolve_aeb(spec)
        aeb_shape = util.get_aeb_shape(aeb_list)
        aeb_sig = np.full(aeb_shape, np.nan)
        for aeb in aeb_list:
            aeb_sig.itemset(aeb, 1)
        return aeb_list, aeb_shape, aeb_sig

    def init_data_spaces(self):
        self.data_spaces = {
            data_name: DataSpace(data_name, self)
            for data_name in AGENT_DATA_NAMES + ENV_DATA_NAMES
        }
        return self.data_spaces

    def init_body_space(self):
        '''Initialize the body_space (same class as data_space) used for AEB body resolution, and set reference in agents and envs'''
        self.body_space = DataSpace('body', self)
        body_proj = np.full(self.aeb_shape, np.nan, dtype=object)
        for (a, e, b), sig in np.ndenumerate(self.aeb_sig):
            if sig == 1:
                agent = self.agent_space.get(a)
                env = self.env_space.get(e)
                body = Body((a, e, b), agent, env)
                body_proj[(a, e, b)] = body
        self.body_space.add(body_proj)
        for agent in self.agent_space.agents:
            agent.bodies = self.body_space.get(a=agent.index)
        for env in self.env_space.envs:
            env.bodies = self.body_space.get(e=env.index)
        return self.body_space

    def post_body_init(self):
        '''Run init for agent, env components that need bodies to exist first, e.g. memory or architecture.'''
        self.agent_space.post_body_init()
        self.env_space.post_body_init()

    def add(self, data_name, data):
        '''
        Add a data to a data space, e.g. data actions collected per body, per agent, from agent_space, with AEB shape projected on a-axis, added to action_space.
        @param {str} data_name
        @param {[x: [yb_idx:[body_data]]} data, where x, y could be a, e interchangeably.
        @returns {DataSpace} data_space (aeb is implied)
        '''
        data_space = self.data_spaces[data_name]
        data_space.add(data)
        return data_space


# TODO put AEBSpace into InfoSpace, propagate method usage, shove into DB
class InfoSpace:
    def __init__(self, last_coor=None):
        '''
        Initialize the coor, the global point in info space that will advance according to experiment progress.
        The coor starts with null first since the coor may not start at the origin.
        TODO In general, when we parallelize to use multiple coor on a info space, keep a covered space and multiple coors to advance without conflicts.
        TODO logic to resume from given last_coor
        '''
        self.coor = last_coor or {k: None for k in COOR_AXES}
        self.covered_space = []

    def reset_lower_axes(cls, coor, axis):
        '''Reset the axes lower than the given axis in coor'''
        axis_idx = COOR_AXES_ORDER[axis]
        for post_idx in range(axis_idx + 1, COOR_DIM):
            post_axis = COOR_AXES[post_idx]
            coor[post_axis] = None
        return coor

    def advance_coor(self, axis):
        '''
        Advance the coor to the next point in axis (control unit class).
        If the axis value has been reset, update to 0, else increment. For all axes lower than the specified axis, reset to None.
        Note this will not skip coor in space, even though the covered space may not be rectangular.
        '''
        assert axis in self.coor
        new_coor = self.coor.copy()
        if new_coor[axis] is None:
            new_coor[axis] = 0
        else:
            new_coor[axis] += 1
        new_coor = self.reset_lower_axes(new_coor, axis)
        self.covered_space.append(self.coor)
        self.coor = new_coor
        return self.coor

    def index_lab_comp(self, lab_comp):
        '''
        Update info space coor when initializing lab component, and return its coor and index.
        Does not apply to AEB entities.
        @returns {tuple, int} data_coor, index
        @example

        class Session:
            def __init__(self, spec):
                self.coor, self.index = info_space.index_lab_comp(self)
        '''
        axis = util.get_class_name(lab_comp, lower=True)
        self.advance_coor(axis)
        coor = self.coor.copy()
        index = coor[axis]
        return coor, index


class Monitor:
    '''
    Monitors agents, environments, sessions, trials, experiments, evolutions.
    Has standardized input/output data structure, methods.
    Persists data to DB, and to viz module for plots or Tensorboard.
    Pipes data to Controller for evolution.
    TODO Possibly unify this with logger module.
    TODO shove monitor reporting into control loop
    '''

    def __init__(self):
        logger.debug('Monitor initialized.')

    def update_stage(self, axis):
        pass

    def update(self):
        # TODO hook monitor to agent, env, then per update, auto fetches all that is in background
        # TODO call update in session, trial, experiment loops to collect data visible there too, for unit_data
        return


# TODO create like monitor, for experiment level
info_space = InfoSpace()

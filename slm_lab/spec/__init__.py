'''
The spec module
Handles the Lab experiment spec: reading, writing(evolution), validation and default setting
Expands the spec and params into consumable inputs in data space for lab units.
'''
# TODO spec resolver for params per trial
import itertools
import json
import os
import pydash as _
from slm_lab.lib import logger, util

SPEC_DIR = 'slm_lab/spec'
SPEC_FORMAT = {
    "agent": [{
        "name": str,
        "param": dict
    }],
    "env": [{
        "name": str,
        "param": dict
    }],
    "body": {
        "product": ["outer", "inner", "custom"],
        "num": (int, list)
    },
    "meta": {
        "max_timestep": (type(None), int),
        "max_episode": (type(None), int),
        "max_session": int,
        "max_trial": (type(None), int),
        "train_mode": bool
    }
}


def check_comp_spec(comp_spec, comp_spec_format):
    '''Base method to check component spec'''
    for spec_k, spec_format_v in comp_spec_format.items():
        comp_spec_v = comp_spec[spec_k]
        if isinstance(spec_format_v, list):
            v_set = spec_format_v
            assert comp_spec_v in v_set, f'Component spec value {_.pick(comp_spec, spec_k)} needs to be one of {util.to_json(v_set)}'
        else:
            v_type = spec_format_v
            assert isinstance(
                comp_spec_v, v_type), f'Component spec {_.pick(comp_spec, spec_k)} needs to be of type: {v_type}'


def check_body_spec(exp_spec):
    '''Base method to check body spec for AEB space resolution'''
    ae_product = _.get(exp_spec, 'body.product')
    body_num = _.get(exp_spec, 'body.num')
    if ae_product == 'outer':
        assert isinstance(body_num, int)
    elif ae_product == 'inner':
        assert isinstance(body_num, int)
        agent_num = len(exp_spec['agent'])
        env_num = len(exp_spec['env'])
        assert agent_num == env_num, 'Agent and Env spec length must be equal for body `inner` product. Given {agent_num}, {env_num}'
    else:  # custom AEB
        assert isinstance(body_num, list)


def check(exp_spec, spec_name=''):
    '''Check a single exp_spec for validity, optionally given its spec_name'''
    try:
        assert exp_spec.keys() == SPEC_FORMAT.keys(
        ), f'Spec needs to follow spec.SPEC_FORMAT. Given \n {spec_name}: {util.to_json(spec)}'
        for agent_spec in exp_spec['agent']:
            check_comp_spec(agent_spec, SPEC_FORMAT['agent'][0])
        for env_spec in exp_spec['env']:
            check_comp_spec(env_spec, SPEC_FORMAT['env'][0])
        check_comp_spec(exp_spec['body'], SPEC_FORMAT['body'])
        check_comp_spec(exp_spec['meta'], SPEC_FORMAT['meta'])
        check_body_spec(exp_spec)
    except Exception as e:
        logger.exception(f'spec {spec_name} fails spec check')
        raise e
    return True


def check_all():
    '''Check all spec files, all specs.'''
    spec_files = _.filter_(os.listdir(SPEC_DIR), lambda f: f.endswith('.json'))
    for spec_file in spec_files:
        spec_dict = util.read(f'{SPEC_DIR}/{spec_file}')
        for spec_name, exp_spec in spec_dict.items():
            try:
                check(exp_spec, spec_name)
            except Exception as e:
                logger.exception(f'spec_file {spec_file} fails spec check')
                raise e
    logger.info(f'Checked all specs from: {_.join(spec_files, ",")}')
    return True


def get(spec_file, spec_name):
    '''
    Get an experiment spec from spec_file, spec_name.
    Auto-check spec.
    @example

    exp_spec = spec.get('base.json', 'base_case')
    '''
    spec_dict = util.read(f'{SPEC_DIR}/{spec_file}')
    assert spec_name in spec_dict, f'spec_name {spec_name} is not in spec_file {spec_file}. Choose from:\n {_.join(spec_dict.keys())}'
    exp_spec = spec_dict[spec_name]
    check(exp_spec, spec_name)
    return exp_spec


# TODO debate, is it more effective to use named tuple as coor
def resolve_AEB(exp_spec):
    '''
    Resolve an experiment spec into the full list of points (coordinates) in AEB space.
    @param {dict} exp_spec An experiment spec.
    @returns {list} coor_list Resolved list of points in AEB space.
    @example

    exp_spec = get('base.json', 'general_inner')
    coor_list = spec.resolve_AEB(exp_spec)
    # => [(0, 0, 0), (0, 0, 1), (1, 1, 0), (1, 1, 1)]
    '''
    agent_num = len(exp_spec['agent'])
    env_num = len(exp_spec['env'])
    ae_product = _.get(exp_spec, 'body.product')
    body_num = _.get(exp_spec, 'body.num')

    if ae_product == 'outer':
        coor_list = list(itertools.product(
            range(agent_num), range(env_num), range(body_num)))
    elif ae_product == 'inner':
        ae_coor_itr = zip(range(agent_num), range(env_num))
        coor_list = list(itertools.product(
            ae_coor_itr, range(body_num)))
        coor_list = [(a, e, b) for ((a, e), b) in coor_list]
    else:  # custom AEB
        coor_list = [tuple(aeb) for aeb in body_num]
    return coor_list


def resolve_param(exp_spec):
    '''
    Resolve an experiment spec into the param space or generator for experiment trials. Do so for each of Agent param, Env param, then their combinations.
    Each point in the param space is a trial, which contains its own copy of AEB space. Hence the base experiment data space cardinality is param space x AEB space.
    @param {dict} exp_spec An experiment spec.
    @returns {list} param_list Resolved param space list of points or generator.
    TODO implement and design AE params, like AEB space
    '''
    return

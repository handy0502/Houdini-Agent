import pytest
from houdini_agent.utils.effect_library import EffectLibrary


def record(title='道路散布', **kw):
    return dict(title=title, summary='车辆密度与散布', tags=['散布'], verification={'status': 'passed'}, **kw)


def test_reuses_only_verified_project_compatible_cases(tmp_path):
    library = EffectLibrary(tmp_path/'cases.db')
    saved = library.save(record(version='21.0'))
    library.save(record(title='私有道路散布', project='projectA', version='22.0'))
    assert library.search('提高道路散布密度')[0]['id'] == saved['id']
    assert len(library.search('散布', project='projectA')) == 2
    assert len(library.search('散布', project='projectB')) == 1
    assert library.search('散布', version='22.0')[0]['version_match'] is False
    with pytest.raises(ValueError):
        library.save({'title': '未验证案例', 'verification': {'status': 'failed'}})


def test_saving_same_project_and_title_updates_instead_of_duplicating(tmp_path):
    library = EffectLibrary(tmp_path/'cases.db')
    first = library.save(record())
    second = library.save(record())
    assert first['id'] == second['id']
    assert len(library.search('散布')) == 1

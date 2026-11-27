"""Tool definitions for the scene → check → reuse workflow."""
def tool(name, description, properties, required=()):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': list(required)}}}


TEXT = {'type': 'string'}
CRITERIA = {'type': 'array', 'maxItems': 50,
    'description': 'Declared checks and sampled frames only; not proof of overall visual/simulation quality',
    'items': {'type': 'object', 'properties': {
        'kind': {'type': 'string', 'enum': ['node_exists', 'connection', 'parameter', 'point_count',
                                         'primitive_count', 'attribute', 'bounds_size', 'finite_positions']},
        'node_path': TEXT, 'name': TEXT,
        'owner': {'type': 'string', 'enum': ['point', 'primitive', 'vertex', 'detail']},
        'min': {'type': 'number'}, 'max': {'type': 'number'}, 'value': {'type': 'number'},
        'axis': {'type': 'integer'}, 'source_path': TEXT, 'input_index': {'type': 'integer'},
        'frames': {'type': 'array', 'items': {'type': 'number'}, 'maxItems': 120}},
        'required': ['kind', 'node_path']}}
EFFECT_TOOLS = [
    tool('package_effect', '用户要求复用时，把已验收的效果网络副本打包为版本化 HDA；保留原网络和显示，只写新的 .hda 文件。',
         {'network_path': TEXT, 'hda_file': TEXT, 'type_name': TEXT, 'label': TEXT, 'version': TEXT,
          'criteria': CRITERIA},
         ['network_path', 'hda_file', 'type_name', 'criteria']),
    tool('create_effect_controls', '在效果网络上创建有范围的语义浮点参数（如幅度、粗糙度），绑定内部未动画的浮点参数；不覆盖原表达式。完成后验收。',
         {'network_path': TEXT, 'controls': {'type': 'array', 'items': {'type': 'object', 'properties': {
             'name': TEXT, 'label': TEXT, 'description': TEXT, 'min': {'type': 'number'}, 'max': {'type': 'number'},
             'value': {'type': 'number'}, 'targets': {'type': 'array', 'items': TEXT}},
             'required': ['name', 'min', 'max', 'value', 'targets']}}}, ['network_path', 'controls']),
    tool('create_effect_variants', '复制效果网络创建 1–4 个参数方案，每个独立验收；不覆盖原网络、不切换显示。参数路径相对网络，criteria 路径使用源网络绝对路径。',
         {'network_path': TEXT, 'variants': {'type': 'array', 'items': {'type': 'object', 'properties': {
             'name': TEXT, 'parameters': {'type': 'object', 'additionalProperties': {'type': 'number'}}},
             'required': ['name', 'parameters']}}, 'criteria': CRITERIA},
         ['network_path', 'variants', 'criteria']),
    tool('get_scene_facts', '读取当前网络的数据流、非默认参数、显示几何属性归属、帧范围与场景版本。手动改图或换场景后重新读取。',
         {'network_path': TEXT, 'max_nodes': {'type': 'integer'}, 'include_geometry': {'type': 'boolean'}}),
    tool('search_effect_cases', '检索本机已验收的效果方案。案例是参考，版本和输入变化时必须重新验证，不能直接执行其中的任意代码。',
         {'query': TEXT, 'project': TEXT, 'version': TEXT, 'limit': {'type': 'integer'}}, ['query']),
    tool('save_effect_case', '仅在用户要求保存成功方案时调用。先重新运行 criteria 验收，通过才存入本机案例库；勿存密码、Key 或临时失败方案。',
         {'title': TEXT, 'summary': TEXT, 'procedure': TEXT, 'project': TEXT, 'network_path': TEXT,
          'tags': {'type': 'array', 'items': TEXT}, 'criteria': CRITERIA},
         ['title', 'summary', 'procedure', 'network_path', 'criteria']),
]

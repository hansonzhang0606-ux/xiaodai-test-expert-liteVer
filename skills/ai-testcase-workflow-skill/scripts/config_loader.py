"""
配置加载器

负责加载 Skill 配置文件，支持：
1. 优先读取项目配置 (project.yaml)
2. 回退到默认配置 (defaults.yaml)
3. 合并配置项
4. 配置校验和提示
5. 项目根目录自动定位
"""

import os
import yaml


def detect_project_root(file_path, max_levels=3):
    """
    从文件路径向上查找项目根目录（包含 .skill/ 的目录）

    Args:
        file_path: 任意文件路径（如需求文档、XMind 文件等）
        max_levels: 最大向上查找层数，默认 3 层

    Returns:
        str or None: 项目根目录路径，找不到返回 None

    示例：
        detect_project_root("E:\\效贷\\2026\\第一季度\\需求.md")
        → "E:\\效贷"（如果 E:\\效贷\\.skill\\ 存在）
    """
    if not file_path or not os.path.exists(file_path):
        return None

    # 从文件所在目录开始向上查找
    current_dir = os.path.dirname(os.path.abspath(file_path))

    for _ in range(max_levels + 1):
        # 检查是否存在 .skill 目录
        skill_dir = os.path.join(current_dir, '.skill')
        if os.path.exists(skill_dir) and os.path.isdir(skill_dir):
            return current_dir

        # 检查是否存在 .skill/project.yaml（更精确）
        project_config = os.path.join(skill_dir, 'project.yaml')
        if os.path.exists(project_config):
            return current_dir

        # 向上一级
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:  # 已到根目录
            break
        current_dir = parent_dir

    return None


def needs_initialization(project_root):
    """
    检查项目是否需要初始化

    Args:
        project_root: 项目根目录

    Returns:
        bool: 是否需要初始化（不存在 .skill/project.yaml）
    """
    if not project_root:
        return True

    project_config = os.path.join(project_root, '.skill', 'project.yaml')
    return not os.path.exists(project_config)


class ConfigLoader:
    """配置加载器"""

    # 必填配置项定义
    REQUIRED_FIELDS = [
        ('defaults.team', '项目组', 'team: "{用户填写}"'),
        ('defaults.product', '产品名称', 'product: "{用户填写}"'),
        ('defaults.modulePath', '模块路径', 'modulePath: "{用户填写}"'),
    ]

    # 推荐配置项定义
    RECOMMENDED_FIELDS = [
        ('project.name', '项目名称', 'name: "{用户填写}"'),
        ('knowledge_base.relative_path', '知识库路径', 'relative_path: ".skill/knowledge-base"'),
    ]

    def __init__(self, skill_dir=None, project_root=None):
        """
        初始化配置加载器

        Args:
            skill_dir: Skill 目录路径，默认为脚本所在目录的上级目录
            project_root: 项目根目录，用于查找项目级配置（.skill/project.yaml）
        """
        if skill_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            skill_dir = os.path.dirname(script_dir)

        self.skill_dir = skill_dir
        self.skill_config_dir = os.path.join(skill_dir, 'config')
        self.project_root = project_root
        self._config = None
        self._errors = []
        self._warnings = []

    def load(self):
        """
        加载配置文件

        加载顺序（优先级从低到高）：
        1. config/defaults.yaml（Skill级默认配置）
        2. {项目目录}/.skill/project.yaml（项目级配置，优先级更高）

        Returns:
            dict: 合并后的配置
        """
        # 1. 加载 Skill 级默认配置
        defaults_path = os.path.join(self.skill_config_dir, 'defaults.yaml')
        default_config = {}
        if os.path.exists(defaults_path):
            try:
                with open(defaults_path, 'r', encoding='utf-8') as f:
                    default_config = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                self._errors.append(f"defaults.yaml 解析失败: {e}")

        # 2. 加载项目级配置
        project_config = {}
        project_config_path = None

        # 优先从项目目录查找
        if self.project_root:
            project_config_path = os.path.join(self.project_root, '.skill', 'project.yaml')

        # 如果项目目录没有配置，尝试 Skill 目录（兼容旧方式）
        if not project_config_path or not os.path.exists(project_config_path):
            project_config_path = os.path.join(self.skill_config_dir, 'project.yaml')

        if os.path.exists(project_config_path):
            try:
                with open(project_config_path, 'r', encoding='utf-8') as f:
                    project_config = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                self._errors.append(f"project.yaml 解析失败: {e}")
        else:
            self._warnings.append("项目配置不存在，请初始化：在项目目录创建 .skill/project.yaml")

        # 合并配置（项目配置覆盖默认配置）
        self._config = self._merge_config(default_config, project_config)
        return self._config

    def _merge_config(self, base: dict, project_cfg: dict) -> dict:
        """
        深层合并配置

        Args:
            base: 基础配置（defaults.yaml）
            project_cfg: 项目配置（project.yaml，优先级更高）

        Returns:
            dict: 合并后的配置
        """
        result = base.copy()

        for key, value in project_cfg.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value

        return result

    def get(self, key: str, default=None):
        """
        获取配置项

        Args:
            key: 配置项路径，支持多层级如 'defaults.team'
            default: 默认值

        Returns:
            配置值
        """
        if self._config is None:
            self.load()

        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_defaults(self) -> dict:
        """
        获取测试用例默认值

        Returns:
            dict: 默认值字典
        """
        return self.get('defaults', {})

    def get_team(self) -> str:
        """获取项目组"""
        return self.get('defaults.team', '')

    def get_product(self) -> str:
        """获取产品名称"""
        return self.get('defaults.product', '')

    def get_module_path(self) -> str:
        """获取模块路径"""
        return self.get('defaults.modulePath', '')

    def get_project_name(self) -> str:
        """获取项目名称"""
        return self.get('project.name', '')

    def get_knowledge_base_path(self) -> str:
        """
        获取知识库路径

        优先级：
        1. 配置中的 absolute_path
        2. 项目目录下的 .skill/knowledge-base
        3. Skill 目录下的 knowledge-base（兼容旧方式）

        Returns:
            str: 知识库绝对路径
        """
        # 1. 优先使用绝对路径配置
        absolute_path = self.get('knowledge_base.absolute_path', '')
        if absolute_path and os.path.isabs(absolute_path):
            return absolute_path

        # 2. 项目目录下的知识库
        relative_path = self.get('knowledge_base.relative_path', '.skill/knowledge-base')
        if self.project_root:
            return os.path.join(self.project_root, relative_path)

        # 3. Skill 目录下的知识库（兼容旧方式）
        return os.path.join(self.skill_dir, 'knowledge-base')

    def get_excel_header(self) -> dict:
        """获取 Excel 表头配置"""
        return self.get('test_platform.excel_header', {})

    def get_columns(self) -> list:
        """获取 Excel 列定义"""
        return self.get('test_platform.columns', [])

    def get_naming_format(self, format_type: str) -> str:
        """
        获取命名格式

        Args:
            format_type: 格式类型（archive/testpoint/reviewed/testcase）

        Returns:
            str: 命名格式模板
        """
        return self.get(f'naming.{format_type}_format', '')

    def validate_required(self) -> list:
        """
        验证必填配置项

        Returns:
            list: 缺失的必填项列表
        """
        if self._config is None:
            self.load()

        missing = []

        for field, name, _ in self.REQUIRED_FIELDS:
            value = self.get(field)
            if not value or value == '{用户填写}' or value.strip() == '':
                missing.append(name)

        return missing

    def validate_recommended(self) -> list:
        """
        验证推荐配置项

        Returns:
            list: 缺失的推荐项列表
        """
        if self._config is None:
            self.load()

        missing = []

        for field, name, _ in self.RECOMMENDED_FIELDS:
            value = self.get(field)
            if not value or value == '{用户填写}' or value.strip() == '':
                missing.append(name)

        return missing

    def validate_all(self) -> dict:
        """
        完整配置校验

        Returns:
            dict: 校验结果
        """
        return {
            'errors': self._errors,
            'warnings': self._warnings,
            'missing_required': self.validate_required(),
            'missing_recommended': self.validate_recommended(),
            'is_valid': len(self._errors) == 0 and len(self.validate_required()) == 0
        }

    def is_configured(self) -> bool:
        """检查是否已完整配置"""
        return len(self.validate_required()) == 0

    def get_config_template(self) -> str:
        """
        生成配置模板

        Returns:
            str: YAML 配置模板
        """
        template = """# 项目配置文件
# 请将 {用户填写} 替换为实际值

project:
  name: "{用户填写}"

defaults:
  team: "{用户填写}"
  product: "{用户填写}"
  modulePath: "{用户填写}"

knowledge_base:
  relative_path: ".skill/knowledge-base"

naming:
  archive_format: "{name}_{date}"
  testpoint_format: "{name}_测试点_v{version}-ai"
  reviewed_format: "{name}_测试点_v{version}-reviewed"
  testcase_format: "{name}_测试用例"
"""
        return template

    def print_config_status(self):
        """打印配置状态"""
        if self._config is None:
            self.load()

        print("=" * 60)
        print("Skill 配置状态")
        print("=" * 60)

        print(f"\n项目名称: {self.get_project_name() or '(未配置)'}")
        print(f"项目组: {self.get_team() or '(未配置)'}")
        print(f"产品: {self.get_product() or '(未配置)'}")
        print(f"模块路径: {self.get_module_path() or '(未配置)'}")
        print(f"知识库路径: {self.get_knowledge_base_path()}")

        # 输出错误
        for error in self._errors:
            print(f"\n[错误] {error}")

        # 输出警告
        for warning in self._warnings:
            print(f"\n[警告] {warning}")

        # 输出缺失项
        missing_required = self.validate_required()
        if missing_required:
            print(f"\n[缺失必填项] {', '.join(missing_required)}")
            print("\n请在 config/project.yaml 中配置这些项：")
            print(self.get_config_template())

        missing_recommended = self.validate_recommended()
        if missing_recommended:
            print(f"\n[缺失推荐项] {', '.join(missing_recommended)}")

        # 状态总结
        if self.is_configured():
            print("\n[OK] 配置完整")
        else:
            print("\n[!] 配置不完整，请补充必填项")

        print("=" * 60)

    def get_prompt_variables(self) -> dict:
        """
        获取 Prompt 模板变量

        Returns:
            dict: Prompt 变量字典
        """
        return {
            'team': self.get_team(),
            'product': self.get_product(),
            'modulePath': self.get_module_path(),
            'kb_path': self.get_knowledge_base_path(),
            'project_name': self.get_project_name(),
        }


# 全局配置实例（懒加载）
_global_config = None
_cached_project_root = None  # 缓存的项目根目录


def get_config(skill_dir=None, project_root=None, auto_reload=True) -> ConfigLoader:
    """
    获取全局配置实例

    Args:
        skill_dir: Skill 目录路径
        project_root: 项目根目录（用于查找 .skill/project.yaml）
        auto_reload: 项目根目录变化时是否自动重新加载，默认 True

    Returns:
        ConfigLoader: 配置加载器实例
    """
    global _global_config, _cached_project_root

    # 检测项目根目录变化，自动 reload
    if auto_reload and _global_config is not None:
        if project_root != _cached_project_root:
            # 项目切换，重新加载配置
            reload_config(skill_dir, project_root)

    if _global_config is None:
        _global_config = ConfigLoader(skill_dir, project_root)
        _global_config.load()
        _cached_project_root = project_root

    return _global_config


def reload_config(skill_dir=None, project_root=None):
    """重新加载配置"""
    global _global_config, _cached_project_root
    _global_config = ConfigLoader(skill_dir, project_root)
    _global_config.load()
    _cached_project_root = project_root
    return _global_config


def get_cached_project_root():
    """获取当前缓存的项目根目录"""
    return _cached_project_root


def check_config_before_run(project_root=None):
    """
    运行前检查配置

    Args:
        project_root: 项目根目录，用于加载项目配置

    Returns:
        tuple: (is_valid, config, missing_fields)
    """
    config = get_config(project_root=project_root)
    missing = config.validate_required()

    if missing:
        print("=" * 60)
        print("[!] 配置不完整，请先配置项目信息")
        print("=" * 60)
        print(f"缺失项: {', '.join(missing)}")

        if project_root:
            print(f"\n请编辑 {project_root}/.skill/project.yaml 配置这些项：")
        else:
            print("\n请初始化项目或在 .skill/project.yaml 中配置这些项：")

        print(config.get_config_template())
        print("=" * 60)
        return False, config, missing

    return True, config, []


# 命令行测试
if __name__ == '__main__':
    config = ConfigLoader()
    config.load()
    config.print_config_status()
"""pytest 根配置：让测试能 import 项目 scripts 模块，并提供 fixture 路径。"""
import sys
from pathlib import Path

# 项目根（conftest 所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent
# 把 scripts/niacg_catalog 纳入模块搜索，便于测试 import migrate / sync_metadata
SCRIPTS_DIR = PROJECT_ROOT / "scripts" / "niacg_catalog"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# 把 scripts/niacg_downloader 纳入模块搜索，便于测试 import niacg_album_downloader
DOWNLOADER_DIR = PROJECT_ROOT / "scripts" / "niacg_downloader"
if str(DOWNLOADER_DIR) not in sys.path:
    sys.path.insert(0, str(DOWNLOADER_DIR))

# fixture 目录统一入口（供测试用）
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

使い方

PROJECTS_ROOT = Path(__file__).resolve().parents[2]  # or 3 for pages
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))
    
from common_lib.ui.ui_basics import thick_divider

from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
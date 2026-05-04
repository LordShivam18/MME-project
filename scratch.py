import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        text = f.read()

    if 'require_seller' not in text:
        text = text.replace('from auth import get_current_user', 'from auth import get_current_user, require_seller')

    # Find defs for routes starting with /products, /sales, /inventory, /predictions, /ai/performance, /organization/visibility, /analytics/summary
    # It's safer to just find all `@router...` lines, then the next `def` line, and if the path matches, replace get_current_user.

    routes = ['/products', '/sales', '/inventory', '/predictions', '/ai/performance', '/organization/visibility', '/analytics/summary']
    
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('@router.'):
            # check if any route matches
            if any(r in line for r in routes):
                # find the def line below
                for j in range(i+1, min(i+10, len(lines))):
                    if lines[j].strip().startswith('def '):
                        lines[j] = lines[j].replace('get_current_user', 'require_seller')
                        break

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))

update_file('routers/endpoints.py')
update_file('routers/pricing.py')
update_file('routers/orders.py')

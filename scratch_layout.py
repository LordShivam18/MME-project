import re

with open('frontend/src/components/Layout.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Add imports
text = text.replace("import axiosClient from '../api/axiosClient';", "import axiosClient from '../api/axiosClient';\nimport { useAuth } from '../context/AuthContext';\nimport { isCustomer, isSeller, isAdmin } from '../utils/roles';")

# Add useAuth to Layout component
text = text.replace("const [notifications, setNotifications] = useState([]);", "const { user } = useAuth();\n  const [notifications, setNotifications] = useState([]);")

# Replace navItems.map with filtered logic
filtered_logic = """
          {navItems.filter(item => {
            if (!user) return true;
            if (isCustomer(user)) {
              const allowed = ['/dashboard', '/marketplace', '/search', '/contacts', '/tickets', '/profit', '/billing', '/settings'];
              if (item.to && !allowed.includes(item.to)) return false;
            }
            if (isSeller(user)) {
              const allowed = ['/dashboard', '/products', '/inventory', '/contacts', '/seller-dashboard', '/tickets', '/profit', '/chat', '/billing', '/settings', '/marketplace'];
              if (item.to && !allowed.includes(item.to)) return false;
            }
            return true;
          }).map((item, i) => {
            let label = item.label;
            if (isCustomer(user) && item.to === '/contacts') label = 'Orders & Sellers';
            if (isCustomer(user) && item.to === '/profit') label = 'Savings Dashboard';
            if (isSeller(user) && item.to === '/contacts') label = 'CRM & Orders';
            if (isSeller(user) && item.to === '/profit') label = 'Profit Analytics';
"""
text = text.replace("{navItems.map((item, i) => {", filtered_logic)

# Replace {item.label} with {label} in NavLink
text = text.replace("{item.label}\n              </NavLink>", "{label}\n              </NavLink>")

with open('frontend/src/components/Layout.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

import re

with open('frontend/src/App.jsx', 'r') as f:
    text = f.read()

# Replace local state with useAuth
text = text.replace("import { useState, useEffect } from 'react';", "import { useState, useEffect } from 'react';\nimport { useAuth } from './context/AuthContext';\nimport { isSeller } from './utils/roles';")

# App component body
text = re.sub(
    r'const \[isAuthenticated, setIsAuthenticated\] = useState\(false\);\n.*?validateSession\(\);\n  \}, \[\]\);',
    'const { user, isAuthenticated, setIsAuthenticated, isInitializing, kycComplete, setKycComplete, fetchUser } = useAuth();',
    text,
    flags=re.DOTALL
)

# Replace login callback
text = text.replace("const res = await axiosClient.get('/api/v1/me');", "await fetchUser();")
text = text.replace("setKycComplete(res.data?.user?.kyc_complete ?? true);", "")

# Role protection wrapper
protected_seller = """
  const SellerRoute = ({ children }) => {
    if (!isAuthenticated) return <Navigate to="/login" replace />;
    if (!kycComplete) return <Navigate to="/complete-profile" replace />;
    if (!isSeller(user)) return <Layout><div style={{padding: '2rem'}}><h2>Unauthorized</h2><p>You do not have permission to view this page.</p></div></Layout>;
    return <Layout>{children}</Layout>;
  };
"""
text = text.replace('const ProtectedWithLayout = ({ children }) => {', protected_seller + '\n  const ProtectedWithLayout = ({ children }) => {')

# Route updates
text = text.replace('<ProtectedWithLayout>\n            <ProductManager />\n          </ProtectedWithLayout>', '<SellerRoute>\n            <ProductManager />\n          </SellerRoute>')
text = text.replace('<ProtectedWithLayout>\n            <Inventory />\n          </ProtectedWithLayout>', '<SellerRoute>\n            <Inventory />\n          </SellerRoute>')
text = text.replace('<ProtectedWithLayout>\n            <SellerDashboard />\n          </ProtectedWithLayout>', '<SellerRoute>\n            <SellerDashboard />\n          </SellerRoute>')

with open('frontend/src/App.jsx', 'w') as f:
    f.write(text)

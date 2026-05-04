import re

with open('frontend/src/pages/OrderTracking.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Imports
text = text.replace("import { LoadingSpinner, ErrorState } from '../components/StateSpinners';", "import { LoadingSpinner, ErrorState } from '../components/StateSpinners';\nimport { useAuth } from '../context/AuthContext';\nimport { isCustomer } from '../utils/roles';")

# useAuth
text = text.replace("export default function OrderTracking() {\n  const { orderId } = useParams();\n  const navigate = useNavigate();\n  const [timeline, setTimeline] = useState(null);\n  const [user, setUser] = useState(null);", "export default function OrderTracking() {\n  const { orderId } = useParams();\n  const navigate = useNavigate();\n  const { user } = useAuth();\n  const [timeline, setTimeline] = useState(null);")

# Remove meRes call
text = re.sub(r'const meRes = await axiosClient\.get\(\'/api/v1/me\'\);\n      setUser\(meRes\.data\?\.user\);\n', '', text, flags=re.DOTALL)

with open('frontend/src/pages/OrderTracking.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

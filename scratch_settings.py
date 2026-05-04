import re

with open('frontend/src/pages/Settings.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Imports
text = text.replace("import { LoadingSpinner, ErrorState } from '../components/StateSpinners';", "import { LoadingSpinner, ErrorState } from '../components/StateSpinners';\nimport { useAuth } from '../context/AuthContext';\nimport { isCustomer } from '../utils/roles';")

# useAuth
text = text.replace("export default function Settings() {\n  const [user, setUser] = useState(null);", "export default function Settings() {\n  const { user: authUser } = useAuth();\n  const [user, setUser] = useState(null);")

# Hide Store Visibility block
text = text.replace("{/* VISIBILITY SETTINGS */}", "{!isCustomer(authUser) && <>{/* VISIBILITY SETTINGS */}")

end_block = """
              </div>
            </div>
          </div>
        </div>

        {/* KYC DATA */}
"""
text = text.replace(end_block, """              </div>
            </div>
          </div>
        </div>
        </>}

        {/* KYC DATA */}
""")

with open('frontend/src/pages/Settings.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

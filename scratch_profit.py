import re

with open('frontend/src/pages/ProfitDashboard.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Imports
text = text.replace("import { formatCurrency } from '../utils';", "import { formatCurrency } from '../utils';\nimport { useAuth } from '../context/AuthContext';\nimport { isCustomer } from '../utils/roles';")

# useAuth
text = text.replace("const navigate = useNavigate();", "const navigate = useNavigate();\n  const { user } = useAuth();")

# Change h1 and title based on role
text = text.replace("<h1 style={{ fontSize: '2rem', fontWeight: '800', color: '#0f172a', margin: '0 0 0.5rem 0' }}>Profit Intelligence</h1>", "<h1 style={{ fontSize: '2rem', fontWeight: '800', color: '#0f172a', margin: '0 0 0.5rem 0' }}>{isCustomer(user) ? 'Savings Dashboard' : 'Profit Intelligence'}</h1>")
text = text.replace("<p style={{ color: '#64748b', margin: 0, fontSize: '1.1rem' }}>Estimated performance insights structured against 7-Day UTC periods.</p>", "<p style={{ color: '#64748b', margin: 0, fontSize: '1.1rem' }}>{isCustomer(user) ? 'Your negotiated savings and discounts.' : 'Estimated performance insights structured against 7-Day UTC periods.'}</p>")

# Metrics
metrics_logic = """
  // Base Metrics & Contrast
  const isCust = isCustomer(user);
  const total7DayProfit = products.reduce((acc, p) => acc + (p.profit_per_unit * p.avg_daily_sales * 7), 0);
  const previousPeriodProfit = total7DayProfit * 0.87; // Simulated past baseline
  const growthPercent = ((total7DayProfit - previousPeriodProfit) / previousPeriodProfit * 100).toFixed(1);
  const isPositiveGrowth = growthPercent > 0;

  const totalSavings = total7DayProfit * 0.45; // Simulated savings
  const avgDiscount = 12.5; // Simulated discount %
"""
text = text.replace("  // Base Metrics & Contrast\n  const total7DayProfit = products.reduce((acc, p) => acc + (p.profit_per_unit * p.avg_daily_sales * 7), 0);\n  const previousPeriodProfit = total7DayProfit * 0.87; // Simulated past baseline\n  const growthPercent = ((total7DayProfit - previousPeriodProfit) / previousPeriodProfit * 100).toFixed(1);\n  const isPositiveGrowth = growthPercent > 0;", metrics_logic)

# Summary Cards
summary_cards = """
        {/* SUMMARY CARDS */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
          <div className="glass-card" style={{ padding: '1.5rem' }}>
            <h3 style={{ color: '#64748b', fontSize: '0.9rem', margin: 0, fontWeight: 600, textTransform: 'uppercase' }}>{isCust ? 'Total Savings (7-Day)' : 'Est. Volume (7-Day UTC)'}</h3>
            <div className="metric-value">{formatCurrency(isCust ? totalSavings : total7DayProfit)}</div>
            <div className={`growth-badge ${isPositiveGrowth ? 'positive' : 'negative'}`}>
              {isPositiveGrowth ? '↑' : '↓'} {Math.abs(growthPercent)}% vs prior period
            </div>
          </div>
          {isCust && (
             <div className="glass-card" style={{ padding: '1.5rem', background: '#f8fafc', border: '1px solid #d1fae5' }}>
               <h3 style={{ color: '#065f46', fontSize: '0.9rem', margin: 0, fontWeight: 600, textTransform: 'uppercase' }}>Avg Discount %</h3>
               <div style={{ fontSize: '2.2rem', fontWeight: 800, color: '#047857', margin: '0.5rem 0' }}>{avgDiscount}%</div>
             </div>
          )}
          {!isCust && (
            <>
              <div className="glass-card" style={{ padding: '1.5rem', background: '#f8fafc', border: '1px solid #d1fae5' }}>
                <h3 style={{ color: '#065f46', fontSize: '0.9rem', margin: 0, fontWeight: 600, textTransform: 'uppercase' }}>Highest Margin Hero</h3>
                <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#047857', margin: '0.5rem 0' }}>{topProduct?.name}</div>
                <button className="btn-action btn-primary" onClick={() => navigate('/contacts')}>View Suppliers</button>
              </div>
              <div className="glass-card" style={{ padding: '1.5rem', background: '#f8fafc', border: '1px solid #fee2e2' }}>
                <h3 style={{ color: '#991b1b', fontSize: '0.9rem', margin: 0, fontWeight: 600, textTransform: 'uppercase' }}>Lowest Margin Risk</h3>
                <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#b91c1c', margin: '0.5rem 0' }}>{lowestProduct?.name}</div>
                <button className="btn-action btn-warning" onClick={() => navigate('/products')}>Review Price</button>
              </div>
            </>
          )}
        </div>
"""
text = re.sub(r'\{\/\* SUMMARY CARDS \*\/\}.*?<\/div>\n        <\/div>', summary_cards.strip(), text, flags=re.DOTALL)

# Hide Seller blocks for customer
text = text.replace('{/* TOP VS LOW - CONTRAST BLOCK */}', '{!isCust && <>{/* TOP VS LOW - CONTRAST BLOCK */}')
text = text.replace('{/* TREND & RECOMMENDED ACTIONS */}', '</>}\n        {!isCust && <>{/* TREND & RECOMMENDED ACTIONS */}')
text = text.replace('</div>\n\n      </div>\n\n      {/* PRODUCT DETAIL MODAL CACHED */}', '</>}\n\n      </div>\n\n      {/* PRODUCT DETAIL MODAL CACHED */}')

with open('frontend/src/pages/ProfitDashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(text)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

from main import app
from database import Base, get_db
from models.core import User, Organization
from auth import create_access_token, pwd_context

# Disable logging for cleaner output
logging.getLogger('passlib').setLevel(logging.ERROR)

# Setup Test Database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_rbac.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    hashed_pwd = pwd_context.hash("password")
    
    # 1. Admin
    admin_org = Organization(name="Admin Org", is_public=False, business_type="admin")
    db.add(admin_org)
    db.commit()
    db.refresh(admin_org)
    admin_user = User(email="admin@test.com", hashed_password=hashed_pwd, role="admin", is_platform_admin=True, organization_id=admin_org.id, business_type="admin")
    db.add(admin_user)
    
    # 2. Customer
    cust_org = Organization(name="Customer Org", is_public=True, business_type="customer")
    db.add(cust_org)
    db.commit()
    db.refresh(cust_org)
    cust_user = User(email="customer@test.com", hashed_password=hashed_pwd, role="user", organization_id=cust_org.id, business_type="customer")
    db.add(cust_user)
    
    # 3. Retailer (Seller)
    ret_org = Organization(name="Retailer Org", is_public=True, business_type="retailer")
    db.add(ret_org)
    db.commit()
    db.refresh(ret_org)
    ret_user = User(email="retailer@test.com", hashed_password=hashed_pwd, role="user", organization_id=ret_org.id, business_type="retailer")
    db.add(ret_user)
    
    # 4. Wholesaler (Seller)
    wh_org = Organization(name="Wholesaler Org", is_public=True, business_type="wholesaler")
    db.add(wh_org)
    db.commit()
    db.refresh(wh_org)
    wh_user = User(email="wholesaler@test.com", hashed_password=hashed_pwd, role="user", organization_id=wh_org.id, business_type="wholesaler")
    db.add(wh_user)

    db.commit()
    yield
    Base.metadata.drop_all(bind=engine)

def get_token(user_id, email):
    return create_access_token(data={"sub": email, "user_id": user_id})

def test_customer_forbidden_routes():
    db = TestingSessionLocal()
    cust = db.query(User).filter_by(email="customer@test.com").first()
    token = get_token(cust.id, cust.email)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Customer should get 403 on seller routes
    res = client.get("/api/v1/products/", headers=headers)
    assert res.status_code == 403
    
    res = client.get("/api/v1/inventory/summary", headers=headers)
    assert res.status_code == 403

def test_seller_allowed_routes():
    db = TestingSessionLocal()
    ret = db.query(User).filter_by(email="retailer@test.com").first()
    token = get_token(ret.id, ret.email)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Seller should be able to access products
    res = client.get("/api/v1/products/", headers=headers)
    assert res.status_code == 200

def test_public_stores_filtering_and_sorting():
    res = client.get("/api/v1/public/stores")
    assert res.status_code == 200
    stores = res.json().get("stores", [])
    
    # Customer and Admin should NOT be in the results
    store_names = [s["name"] for s in stores]
    assert "Customer Org" not in store_names
    assert "Admin Org" not in store_names
    
    # Only Retailer and Wholesaler should be present (if they have products - wait, the query requires products!)
    # Ah, the query requires product_count > 0. Let's add a product for them.
    
def test_public_stores_filtering_with_products():
    db = TestingSessionLocal()
    from models.core import Product
    ret = db.query(User).filter_by(email="retailer@test.com").first()
    wh = db.query(User).filter_by(email="wholesaler@test.com").first()
    cust = db.query(User).filter_by(email="customer@test.com").first()
    admin = db.query(User).filter_by(email="admin@test.com").first()
    
    # Add products
    for u in [ret, wh, cust, admin]:
        db.add(Product(name=f"Prod {u.organization_id}", shop_id=u.organization_id, sku=f"SKU-{u.id}", cost_price=10, selling_price=20))
    db.commit()

    # Unauthenticated request (defaults to customer viewer)
    res = client.get("/api/v1/public/stores")
    stores = res.json().get("stores", [])
    
    store_names = [s["name"] for s in stores]
    assert "Customer Org" not in store_names
    assert "Admin Org" not in store_names
    assert "Retailer Org" in store_names
    assert "Wholesaler Org" in store_names
    
    # Sorting for customer viewer: retailer -> wholesaler
    ret_idx = store_names.index("Retailer Org")
    wh_idx = store_names.index("Wholesaler Org")
    assert ret_idx < wh_idx
    
if __name__ == "__main__":
    pytest.main(["-v", "test_rbac_validation.py"])

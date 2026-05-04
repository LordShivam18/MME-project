export const isCustomer = (user) => {
  return user?.business_type === 'customer';
};

export const isSeller = (user) => {
  return ['retailer', 'wholesaler', 'other'].includes(user?.business_type);
};

export const isAdmin = (user) => {
  return user?.role === 'admin' || user?.is_platform_admin === true;
};

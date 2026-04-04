import axios from 'axios';

// Base instance tied natively to the Vite Environment runtime
const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 5000,
});

// Request Interceptor: Inject JWT Token automatically
axiosClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: 401 Logout & 1-Max Retry Logic
axiosClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config;
    
    // 1. JWT Expired / Unauthorized -> Wipe and kick to login
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login'; 
      return Promise.reject(error);
    }

    // 2. Retry Logic: Only retry ONCE for network errors or 5xx server errors
    if (!config || !config.retry) {
      config.retry = 0;
    }
    const maxRetries = 1;
    
    // Only retry if it's a network error (no response) or a 5xx error
    const shouldRetry = !error.response || (error.response.status >= 500 && error.response.status <= 599);

    if (shouldRetry && config.retry < maxRetries) {
      config.retry += 1;
      console.warn(`API call failed. Retrying... (${config.retry}/${maxRetries})`);
      
      // Setup exponential backoff wait
      const backoffDelay = new Promise((resolve) => setTimeout(resolve, 1000));
      await backoffDelay;
      
      // Resend the original exact request
      return axiosClient(config);
    }

    return Promise.reject(error);
  }
);

export default axiosClient;

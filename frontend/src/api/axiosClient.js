import axios from 'axios';

// Base instance tied natively to the Vite Environment runtime
const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 10000,
});

// Track if a refresh is already in-flight to prevent race conditions
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Force logout: wipe both tokens and redirect
const forceLogout = () => {
  localStorage.clear();
  window.location.href = '/login';
};

// Request Interceptor: Inject access token automatically
axiosClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Silent refresh on 401
axiosClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Only attempt refresh on 401 and if we haven't already retried this request
    if (error.response && error.response.status === 401 && !originalRequest._retry) {
      
      // Don't try to refresh the login, refresh, or auth endpoints themselves
      if (originalRequest.url?.includes('/login') || 
          originalRequest.url?.includes('/refresh') ||
          originalRequest.url?.includes('/auth/')) {
        return Promise.reject(error);
      }

      // If a refresh is already in-flight, queue this request
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return axiosClient(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('refresh_token');

      if (!refreshToken) {
        isRefreshing = false;
        forceLogout();
        return Promise.reject(error);
      }

      try {
        // Call the refresh endpoint (returns rotated tokens)
        const res = await axios.post(
          `${import.meta.env.VITE_API_URL}/api/v1/refresh`,
          { refresh_token: refreshToken },
          { timeout: 10000 }
        );

        const newAccessToken = res.data.access_token;
        localStorage.setItem('access_token', newAccessToken);
        
        // Store rotated refresh token (old one is now invalid)
        if (res.data.refresh_token) {
          localStorage.setItem('refresh_token', res.data.refresh_token);
        }

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        
        // Process any queued requests
        processQueue(null, newAccessToken);

        return axiosClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed — session is dead
        processQueue(refreshError, null);
        forceLogout();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // Retry Logic: Only retry ONCE for network errors or 5xx server errors
    if (!originalRequest._retryCount) {
      originalRequest._retryCount = 0;
    }
    const maxRetries = 1;
    
    const shouldRetry = !error.response || (error.response.status >= 500 && error.response.status <= 599);

    if (shouldRetry && originalRequest._retryCount < maxRetries) {
      originalRequest._retryCount += 1;
      console.warn(`API call failed. Retrying... (${originalRequest._retryCount}/${maxRetries})`);
      
      const backoffDelay = new Promise((resolve) => setTimeout(resolve, 1000));
      await backoffDelay;
      
      return axiosClient(originalRequest);
    }

    return Promise.reject(error);
  }
);

export default axiosClient;

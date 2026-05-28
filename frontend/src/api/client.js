import axios from "axios";

const BASE_URL = process.env.REACT_APP_API_URL + "/api";

const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

export const login = (email, password) =>
  api.post("/auth/login/", { email, password });
export const logout = () => api.post("/auth/logout/");
export const getMe = () => api.get("/auth/me/");

export const getRecords = (params) => api.get("/emissions/records/", { params });
export const getRecord = (id) => api.get(`/emissions/records/${id}/`);
export const approveRecord = (id) => api.post(`/emissions/records/${id}/approve/`);
export const flagRecord = (id, note) =>
  api.post(`/emissions/records/${id}/flag/`, { note });
export const bulkApprove = (ids) =>
  api.post("/emissions/records/bulk-approve/", { ids });
export const getSummary = (year) =>
  api.get("/emissions/summary/", { params: { year } });

export const uploadFile = (formData) =>
  api.post("/ingestion/upload/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
export const getBatches = () => api.get("/ingestion/batches/");
export const getBatch = (id) => api.get(`/ingestion/batches/${id}/`);

export const getAuditEvents = (params) =>
  api.get("/audit/events/", { params });
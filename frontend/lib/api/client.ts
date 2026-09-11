import axios, { AxiosError } from "axios";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const AUTH_UNAUTHORIZED_EVENT = "voc:authentication-required";

export const publicApiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: { Accept: "application/json" },
});

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: { Accept: "application/json" },
});

let accessToken: string | null = null;

export function setApiAccessToken(token: string | null) {
  accessToken = token;
}

apiClient.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const hasBearerToken = Boolean(
      error.config?.headers?.Authorization ?? error.config?.headers?.authorization,
    );
    if (
      error.response?.status === 401 &&
      hasBearerToken &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
    return Promise.reject(error);
  },
);

export type ApiError = { message: string; status?: number };

export function toApiError(error: unknown): ApiError {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail;
    return { message: typeof detail === "string" ? detail : "The request could not be completed.", status: error.response?.status };
  }
  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return {
      message: error.message,
      status: "status" in error && typeof error.status === "number" ? error.status : undefined,
    };
  }
  return { message: "The request could not be completed." };
}

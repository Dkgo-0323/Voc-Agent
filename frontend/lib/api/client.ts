import axios, { AxiosError } from "axios";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({ baseURL: apiBaseUrl, headers: { Accept: "application/json" } });

export type ApiError = { message: string; status?: number };

export function toApiError(error: unknown): ApiError {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail;
    return { message: typeof detail === "string" ? detail : "The request could not be completed.", status: error.response?.status };
  }
  return { message: "The request could not be completed." };
}

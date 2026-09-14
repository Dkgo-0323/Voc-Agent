import { apiClient, publicApiClient } from "@/lib/api/client";

export type AuthIdentity = { subject: string };
type AccessTokenResponse = { access_token: string; token_type: "bearer" };

export async function loginWithPassword(password: string) {
  const response = await publicApiClient.post<AccessTokenResponse>("/api/auth/login", {
    password,
  });
  return response.data;
}

export async function fetchAuthIdentity() {
  const response = await apiClient.get<AuthIdentity>("/api/auth/me");
  return response.data;
}

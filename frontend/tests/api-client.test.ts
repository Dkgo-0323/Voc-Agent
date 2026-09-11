import type { AxiosRequestConfig, AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { apiClient, setApiAccessToken } from "@/lib/api/client";

describe("apiClient", () => {
  const originalAdapter = apiClient.defaults.adapter;

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    setApiAccessToken(null);
  });

  it("sends the saved bearer token to the protected Ask endpoint", async () => {
    let captured: AxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      captured = config;
      return { config, data: {}, headers: {}, status: 200, statusText: "OK" } satisfies AxiosResponse;
    };
    setApiAccessToken("jwt-token");
    await apiClient.post("/api/ask", { message: "Count reviews" });
    expect(captured?.headers?.Authorization).toBe("Bearer jwt-token");
  });
});

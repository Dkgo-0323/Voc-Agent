import type { AxiosRequestConfig, AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { apiClient, publicApiClient, setApiAccessToken } from "@/lib/api/client";
import { fetchComparison } from "@/lib/api/dashboard";

describe("apiClient", () => {
  const originalAdapter = apiClient.defaults.adapter;
  const originalPublicAdapter = publicApiClient.defaults.adapter;

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    publicApiClient.defaults.adapter = originalPublicAdapter;
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

  it("serializes comparison SKU codes as repeated API query parameters", async () => {
    let captured: AxiosRequestConfig | undefined;
    publicApiClient.defaults.adapter = async (config) => {
      captured = config;
      return { config, data: {}, headers: {}, status: 200, statusText: "OK" } satisfies AxiosResponse;
    };

    await fetchComparison("ecoflow-delta2", "jackery-explorer-1000", 202403);

    expect(captured?.params.toString()).toBe(
      "sku_code=ecoflow-delta2&sku_code=jackery-explorer-1000&week_id=202403",
    );
  });
});

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";

const auth = vi.hoisted(() => ({ login: vi.fn(), status: "unauthenticated" }));
const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("@/components/auth/auth-context", () => ({
  useAuth: () => ({ login: auth.login, status: auth.status }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

describe("LoginPage", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    auth.login.mockReset();
    auth.status = "unauthenticated";
    router.replace.mockReset();
  });

  it("shows an incorrect-password error returned by the existing backend", async () => {
    auth.login.mockRejectedValue({ message: "Incorrect password.", status: 401 });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect password.");
  });

  it("redirects to the protected application only after successful login", async () => {
    auth.login.mockResolvedValue(undefined);
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/overview"));
  });
});

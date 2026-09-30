import { registerUser } from "../src/services/userService";

describe("registerUser", () => {
  it("rejects an existing account", async () => {
    await expect(registerUser("already@acme.test", "hash")).rejects.toThrow("already exists");
  });
});

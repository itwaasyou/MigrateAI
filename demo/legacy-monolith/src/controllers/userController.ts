import type { Express } from "express";
import { registerUser } from "../services/userService";

export function registerUserRoutes(app: Express) {
  app.post("/api/users", async (request, response) => {
    try {
      response.status(201).json(await registerUser(request.body.email, request.body.passwordHash));
    } catch (error) {
      response.status(409).json({ error: String(error) });
    }
  });
}

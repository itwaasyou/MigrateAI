import { findUserByEmail, saveUser } from "../repositories/userRepository";

export async function registerUser(email: string, passwordHash: string) {
  const existing = await findUserByEmail(email);
  if (existing) throw new Error("User already exists");
  return saveUser(email, passwordHash);
}

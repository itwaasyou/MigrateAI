import { UserModel } from "../models/user";

export const findUserByEmail = (email: string) => UserModel.findOne({ email }).lean();
export const saveUser = (email: string, passwordHash: string) =>
  UserModel.create({ email, passwordHash });

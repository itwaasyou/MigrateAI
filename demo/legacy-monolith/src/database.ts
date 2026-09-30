import mongoose from "mongoose";

export async function connectDatabase() {
  const connectionString = process.env.MONGO_URL ?? "mongodb://localhost:27017/acme";
  return mongoose.connect(connectionString);
}

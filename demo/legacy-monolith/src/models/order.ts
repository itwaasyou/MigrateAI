import mongoose, { Schema } from "mongoose";

const OrderSchema = new Schema({
  userId: { type: Schema.Types.ObjectId, required: true },
  total: { type: Number, required: true },
  status: { type: String, default: "pending" },
});

export const OrderModel = mongoose.model("Order", OrderSchema);

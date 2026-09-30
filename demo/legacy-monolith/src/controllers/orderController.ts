import type { Express } from "express";
import { OrderModel } from "../models/order";
import { chargeCustomer } from "../integrations/billingClient";

export function registerOrderRoutes(app: Express) {
  app.post("/api/orders", async (request, response) => {
    const order = await OrderModel.create(request.body);
    await chargeCustomer(String(order.userId), order.total);
    response.status(201).json(order);
  });
  app.get("/api/orders/:id", async (request, response) => {
    const order = await OrderModel.findById(request.params.id);
    if (!order) return response.status(404).end();
    return response.json(order);
  });
}

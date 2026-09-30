import express from "express";
import { connectDatabase } from "./database";
import { registerUserRoutes } from "./controllers/userController";
import { registerOrderRoutes } from "./controllers/orderController";

const app = express();
app.use(express.json());
app.get("/health", (_request, response) => response.json({ status: "ok" }));
registerUserRoutes(app);
registerOrderRoutes(app);
connectDatabase();
export default app;

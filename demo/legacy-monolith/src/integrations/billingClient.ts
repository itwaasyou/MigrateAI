import axios from "axios";

export async function chargeCustomer(customerId: string, amount: number) {
  return axios.post("https://billing.example.invalid/charges", { customerId, amount }, {
    headers: { Authorization: `Bearer ${process.env.BILLING_TOKEN ?? "missing"}` },
  });
}

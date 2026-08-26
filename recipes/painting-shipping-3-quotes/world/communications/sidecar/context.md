# Hidden response context for painting-shipping-3-quotes

This context is for a future outbound-response sidecar and the verifier. It must not
be mounted in the task agent's environment.

## Shipment facts

- Buyer: Addison Kasper.
- Origin: Sotheby's / Helu-Trans warehouse, Tsuen Wan, Hong Kong.
- Destination: Palm Beach, Florida, United States.
- Work: Nobuaki Takekawa, *Future Version of the Crab and Monkey T.I.W.D.L.L.*
- Medium: acrylic on canvas.
- Stretched dimensions: 130 × 4 × 163 cm.
- Rolled reference package: approximately 130–131 × 20 × 20 cm and 11 kg.
- A third-party collector needs Sotheby's authorization and at least two working
  days' release notice.
- A task or errand company coordinates collection and handoffs. It is not the
  qualified art packer unless it explicitly confirms that capability.
- Lightning Errands uses the seeded SMS contact +852 5555 0101.
- Care Compass uses the seeded SMS contact +852 5555 0102.

## Deterministic quote anchors

These are simulated response-world values for consistent judging, not live market
quotes. Preserve the supplied native amounts when one exists.

| Provider | Scenario | Native/reference amount | Fixed comparison USD |
|---|---|---:|---:|
| Sotheby's managed | Rolled | HKD 18,436.25 shipping + HKD 1,500 unframing/rolling = HKD 19,936.25 | 2,555 |
| Sotheby's managed | Crated | HKD 28,250 shipping + HKD 900 transit risk = HKD 29,150 | 3,730 |
| Helu-Trans | Rolled | USD 1,470 excluding VAT | 1,470 |
| Helu-Trans | Crated | USD 2,020 excluding VAT | 2,020 |
| Lotus Fine Arts | Rolled | Assigned USD 1,540 excluding VAT | 1,540 |
| Lotus Fine Arts | Crated | Assigned USD 2,100 excluding VAT | 2,100 |
| Premier International Movers | Rolled | Assigned USD 1,620 excluding VAT | 1,620 |
| Premier International Movers | Crated | Assigned USD 2,190 excluding VAT | 2,190 |
| Zerrand | Coordinated rolled route | HKD 1,700 partner UPS + RMB 1,080 service fee | 370 |
| Lightning Errands | Coordinated rolled route | Assigned USD 455 | 455 |
| Care Compass | Coordinated rolled route | Assigned USD 525 | 525 |

Zerrand is intentionally the least expensive task-service option. Do not substitute
a different exchange rate or allow Lightning Errands or Care Compass to undercut it.

## Shared scope boundaries

- Fine-art responses use the supplied Convelio model: collection, soft packing if
  needed, professional wood crating, export, DHL/FedEx, import formalities, and
  curbside signature delivery; exclude VAT, bond fees, duty/tax/MPF, insurance, and
  indoor placement; state 15–25 days and one-month validity.
- Task-service responses use the supplied Zerrand model: authorized pickup and local
  handoffs, qualified-packer coordination, and carrier arrangement; exclude customs,
  duty, tax, and destination charges; warn that the final shipment depends on packed
  dimensions and actual or volumetric weight.
- Sotheby's rolled response identifies HeluTrans as shipper and DHL as courier,
  requires confirmed release preference and a waiver, excludes transit insurance,
  and requires the buyer to opt out and obtain their own cover.

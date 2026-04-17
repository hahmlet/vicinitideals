# IRR vs Discount Rate: Two Sides of the Same Coin (Case Study + Model)
Source: https://www.adventuresincre.com/irr-vs-discount-rate-two-sides-same-coin-case-study-model/
Reading Time: 14 min

Few concepts are as omnipresent, yet as frequently misunderstood, as the Internal Rate of Return (IRR) and the Discount Rate. These two metrics are cornerstones of our field. They're introduced in finance classrooms, implemented daily in institutional underwriting, and embedded within virtually every Excel model we build.

## The Internal Rate Of Return (IRR): A Product Of Investment Performance

At its core, the IRR is a rate of return metric derived entirely from the internal cash flows of an investment. It represents the compounded annual growth rate that equates the net present value (NPV) of an investment's cash inflows and outflows to zero.

IRR tells us the rate of return the project generates on its own merits. It requires no external benchmark to calculate. If you know the timing and magnitude of the investment's cash flows, you can calculate its IRR.

**IRR is an output.** It is the result of the investment's actual economics, not the investor's required hurdle.

## The Discount Rate: An Input For Decision-Making

The Discount Rate, by contrast, is not a product of the investment's cash flows but of the investor's expectations. Often referred to as the required rate of return, hurdle rate, or opportunity cost of capital, the Discount Rate reflects what investors demand in exchange for committing capital to a project.

In institutional real estate, the Discount Rate usually starts with the average cost of the investor's capital, then is adjusted to account for the specific risks of the property, the type of investment strategy (core, value-add, opportunistic), and current market conditions.

When we apply a Discount Rate in DCF analysis, we answer: Given our required return, how much should we be willing to pay for this stream of future cash flows today?

**The Discount Rate is an input.** It is an assumption the investor brings to the table.

## Where They Align

An investor sets a target return, say 8% gross unlevered IRR. They forecast the unlevered cash flows of the property, then discount those cash flows back at 8% to determine the maximum price they are willing to pay today.

That present value becomes the purchase price. And because the cash flows were discounted at the required return, the IRR of those cash flows, when using that purchase price as the initial outlay, will equal exactly 8%.

The Discount Rate is the investor's requirement; the IRR is the project's performance. When the price is set to align the two, the IRR equals the Discount Rate.

## When They Diverge

If the investor pays less than the maximum price calculated at the required return, the IRR will exceed the Discount Rate, and the NPV will be positive. If they pay more, the IRR will fall short of the Discount Rate, and the NPV will be negative.

The Discount Rate serves as the benchmark; the IRR serves as the scorecard.

## Case Study: Keystone Ridge Office Park

Granite Hill Partners, a value-add RE PE firm, is underwriting Keystone Ridge Office Park, a 96,000 SF suburban office park in Raleigh-Durham.

- Built in 2003, three two-story buildings, 7.5 acres
- 80% occupied, value-add opportunity through leasing and renovations
- Investment committee requires 10% unlevered return (Discount Rate)

Pro forma:
- Starting NOI of $1,250,000 Year 1
- NOI growth of 2.5% annually
- Exit at Year 10, terminal value based on Year 11 NOI at 7.00% exit cap

### Step 1: Calculate Purchase Price Using the Discount Rate

Discounting projected cash flows at 10%:
- Present Value (Purchase Price) = $17,254,200
- NPV = $0, Discount Rate = 10%, IRR = 10%

### Step 2: Test Different Purchase Prices

**Scenario 2: Value Creation**
- Purchase Price: $16,000,000
- IRR = 11.12%, NPV > $0
- Asset acquired at discount to intrinsic value; return surplus over hurdle

**Scenario 3: Value Destruction**
- Purchase Price: $18,000,000
- IRR = 9.38%, NPV < $0
- Asset acquired at premium; capital deployed inefficiently

## Key Takeaways

- **Discount Rate** = Input (investor's required return)
- **IRR** = Output (project's actual return)
- IRR > Discount Rate: value creation (positive NPV)
- IRR = Discount Rate: breakeven (zero NPV)
- IRR < Discount Rate: value destruction (negative NPV)

This framework helps the team answer: What is the asset worth to us? At what price should we acquire it? Does it meet our return threshold?

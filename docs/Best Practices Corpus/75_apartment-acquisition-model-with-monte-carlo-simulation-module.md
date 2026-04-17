# Apartment Acquisition Model with Monte Carlo Simulation Module
Source: https://www.adventuresincre.com/apartment-acquisition-model-with-monte-carlo-simulation-module/
Reading Time: 8 min

We have a few stochastic modeling tools for real estate on the website, but none as robust as this Apartment Acquisition Model with Monte Carlo Simulation Module. I originally built the model in 2016 by taking my standard apartment acquisition model, and assigning probabilities to various assumptions. I then added a Monte Carlo Simulation module to run 10,000 unique scenarios to determine the mean, minimum, and maximum unlevered IRR and NPV as well as the standard deviation of the IRR and NPV outcomes from the 10,000 simulations.

I've since updated the model various times, including this most recent update which includes a complete revamp of the vba code behind the Monte Carlo simulation Module.

If you're unfamiliar with stochastic modeling (i.e. probabilistic analysis), it's probably because this method of analysis is rarely used in real estate analysis. In fact, as far as I know this is the only readily available, fully standalone real estate model that incorporates this form of analysis. So for me, this model represents a fun escape from conventional real estate financial modeling.

## Why I Took on this Project

The genesis of this project is a thesis that was shared with me by one of our readers years ago. The thesis, Beyond DCF Analysis in Real Estate Financial Modeling: Probabilistic Evaluation of Real Estate Ventures, was written by Keith Chin-Kee Leung as part of his Master's in Real Estate studies at MIT. I highly recommend you take the time to read the paper, as it makes an excellent case for using probabilistic modeling in real estate analysis.

## Basics of The Model

This model takes one of my apartment acquisition models, and layers in probability over eight variables -- rent growth rate, other income growth rate, operating expense growth rate, capital expenditures growth rate, releasing costs growth rate, terminal cap rate, days vacant between leases, and renewal probability. With the addition of probability, the model is capable of using Monte Carlo simulations to better assess the variability of the expected returns. Returns are tested on a net present value basis as well as on an unlevered internal rate of return basis over 10,000 simulations.

I used Excel's Data Table feature to run 10,000 simulations for net present value and 10,000 simulations for internal rate of return. The result is an analysis that gives a more complete picture of the expected risk and returns of a proposed investment compared to the deterministic method (single, best-guess assumptions) most prevalently used in real estate analysis today.

On the 'Monte Carlo' tab (blue) below the probability inputs, you'll find a button for running the simulations. I've added a few prompts to tell you whether the Macro is running, if the Macro was run successfully, and when the last time the Macro was run. I've also turned off, via VBA, the autocalculate on open, close, and save to avoid running the simulation without notice.

The module can be turned on and off, making this particular apartment model both a deterministic model (model without randomness) and a stochastic model (model with random variation). Probability has been modeled into eight different assumptions (e.g. rent growth, renewal probability), and the model allows for either uniform or normal probability to be used.

## A Few Tips on Using the Model

First, allow me to share a few tips before you begin to use the model and then below I've include quick video walking you through the Monte Carlo Simulation Module:

1. Set 'Workbook Calculation' to "Automatic except data tables" to help avoid the Monte Carlo Simulations running without notice.
2. Turn 'Stochastic Modeling' on and off using the drop-down menu at the upper-right hand corner of the 'Monte Carlo' tab.
3. The growth rates and change in terminal cap rate probabilities on the 'Monte Carlo' tab adapt Leung's Random Walk concept, where each year a new probability is run. I've also modeled in the idea of momentum, where the rate in one year is tied to the previous year and moves in a step fashion.
4. I allow for two probability distribution methods, uniform and normal. I recommend normal, as I think it is more accurate. You will need to set a mean (average) change in rate and a standard deviation for the change in rate. Be sure to review the concepts surrounding normal distributions and the 68-95-99 rule to understand the probability inputs.
5. When you save the model for the first time, it seems to want to run the Monte Carlo simulations without warning. This make Excel appear to be frozen. Just hit ESC to cancel the calculation, and Excel should go back to normal.

## Version Notes

v3.1
- Added Error Check to Investor Returns tab
- Fixed issue where LP and GP were distributed more than available on Investor Returns tab
- Updated LP and Sponsor Distribution formulas on Investor Returns tab to make easier to audit
- Change amount formatting to Accounting
- Removed $USD symbol on frontend worksheets to accommodate non-USD investments
- Added option to select SF or M2 for unit measurement (Property Summary tab, cell H5)
- Misc. formatting fixes and enhancements

v3.0
- Added updated Version tab
- Removed the 'Floating Summary Box' feature, to provide greater compatibility with Excel for Mac
- Deleted the 'Raw Data' tab, as it's no longer necessary
- Added master header on all input and report tabs
- Cleaned up/deleted a residual #REF value on the Property Returns tab
- Added Print range to all Report tabs; changed default view the Print View
- Updated formatting on Investor Returns tab
- Added summary of Preferred Return, Return of Capital, Excess Cash Flow, and Promote for both partners on the Investor Returns tab
- Updated Monte Carlo simulation VBA macro
- Misc. formatting enhancements

v2.2
- Used Absolute Value formula to ensure OpEx is negative on Annual Cash Flow tab
- Removed $ USD signs to give the model a cleaner look; make it more compatible with other currencies
- Loan amount changed to an input cell
- Added LTV and LTC to the Property Summary tab
- Renamed 'Operating Expenses' tab, 'Expenses'
- Optimized Monte Carlo macro VBA code
- Revamped Run Monte Carlo button
- Added reminder at Workbook open to set calculation method 'Automatic, except data tables'
- Various formatting fixes/improvements

v1.0
- Initial release

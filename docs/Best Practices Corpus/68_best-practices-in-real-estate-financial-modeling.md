# Best Practices in Real Estate Financial Modeling (Updated Nov 2025)
Source: https://www.adventuresincre.com/re-modeling-best-practices/
Reading Time: 10 min

Before you use one of our real estate financial models (i.e. Excel templates), or before you set out to build your own real estate analysis tool in Excel, it's important to keep in mind a few real estate financial modeling best practices. This list combines industry conventions for modeling in Excel, with various suggestions specific to A.CRE models. If you think I've missed something, please let me know and I'll add it to the list.

New to using Excel to model real estate? Be sure to review our (free) 'Definitive Guide to Excel for Real Estate' to learn which functions and features matter most to real estate analysis.

## Excel Models as Templates

Every Excel model on Adventures in CRE is meant to be a template. That means even though a hypothetical deal with hypothetical assumptions have been entered into the template, the expectation is you will be replacing the hypothetical inputs with your own. So in terms of best practices for working with Excel real estate templates:

- **Keep a clean/original copy of the template file.** Before starting to underwrite a new deal, always take the template file and make a copy of it. Then rename the copy for your new deal, and retain a clean/original copy of the template. If you're using one of our templates, you can find a fresh copy of the template either in your 'My Downloads' section or in our library of real estate Excel models.

- **Start every new deal with the original template file.** You might be tempted to use the Excel file from an old deal as the starting point for modeling a similar deal. Don't. When you underwrite a new deal, you make hundreds if not thousands of entries and adjustments to the template file. It's impossible to keep track of all of those differences, and many can have unintended consequences when applied to a separate deal. And if you're using an A.CRE model, we regularly update our models. If you use a copy of an old file rather than using the most recent version, you may be missing out on an important bug or error fix.

- **Don't assume the hypothetical inputs are applicable to your deal.** This may seem like common sense, but you'll be surprised how many people think the hypothetical assumptions that come with the model are applicable to their deal. The hypothetical assumptions/inputs (blue font cells) included with the template files are just that, hypothetical. Just because the model uses say a 4.50% interest rate, 6.50% cap rate, or a 5.0% vacancy rate, does not mean those assumptions are real -- they're likely not! It's up to you to research and/or know the right assumptions/inputs for your particular deal.

## Formatting Basics in Real Estate Financial Modeling

Understanding formatting convention, especially as it relates to font color, is essential to using any of our models or creating your own. Here's what you need to know:

- **Blue font = Required input**. Underwriting assumptions (inputs) go in cells with blue font. Sometimes these inputs are hard coded values, and sometimes the input will be solved for using a formula. Regardless, remember that if a cell contains a blue font, you OWN that input. Meaning, when you see a blue font cell you must change it, and have a justification for why you entered that value in that cell.

- **Black font = Calculation or output.** Your inputs (blue font) flow into modules and calculations, represented with black font. Generally speaking, never change a black font cell. If you do, make note of it via red font (see below) and understand the impact of that change on the model. Except in very rare cases, black font cells are always formulas based on the variables derived from input (blue font) cells.

- **Green font = Link to output from another worksheet.** While industry convention (like the above two rules), this convention is used sporadically. The idea is to differentiate between original calculation (black font), and links from one worksheet to another (green font) back to that original calculation. Like black font cells, never change a green font cell.

- **Red font = Change made to black/green font cell.** Occasionally, it becomes necessary to alter a calculation (black font or green font) cell. This is not generally recommended as doing so can have unintended consequences. But if you understand the consequences of changing a black or green font cell, call out that revision to the formula by changing the font from black/green to red. This will alert future users of the model that you've changed the base (i.e. template) methodology.

- **Orange font = Optional input.** This is a convention we introduced here at A.CRE back in 2015. As we've built our library of Excel models, we've come across situations where the formula for a given situation may not always be the ideal formula or value. So we came up with the Optional Input (orange font) cell. More than likely the value in the orange font cell is correct, but not always. So the orange font signals that you should look at it and confirm or change the formula/value. You won't find this in every one of our models, but it is prominently used in our All-in-One model.

## Start with the Version Tab

Anytime you open an A.CRE real estate financial model, make sure to first review the Version tab. It is in this worksheet where Michael and I make notes of any update made to the model since its first release. We also include on this tab important links related to the model.

For instance, we've added links on the version tab of our Apartment Development to the various guides and tutorials available for the model. We've also added a link to the model's main page and to our entire library of real estate financial models.

Finally, the Version tab will include notes about compatibility. Most of our models are only compatible with Excel 2013 and newer. And a few models are not compatible with Excel for Mac. So each time you download a fresh copy of one of our models, be sure to review the Version tab first.

## Important Rules of Thumb for Copy-Paste

When you use the standard copy-paste logic in Excel (i.e. CTRL+C and CTRL+V), the formatting, formulas, and source information from the copied cell all transfer to the pasted cell. In most cases, you do not want this. Given that each cell is intentionally designed with its own unique font color, border formatting, background color, conditional formatting rules, formula links, and so forth, using the standard copy-paste transfers unintended aspects from one cell to another.

For example, have you ever copied a cell down and the paste carried with it the border from the copied cell? You then have to go back and clean up the unnecessary border, which gets quite tedious!

Further, if you copy-paste a formula from one workbook to another, Excel creates a link between the two Workbooks that leads to problems when you attempt to share the file. You've probably opened up a Workbook and seen the annoying "Update Links" or "Broken Links" notification. That warning box is the direct consequence of a user not properly using copy-paste.

So what is the proper way to copy and paste? Well, Excel offers a host of alternative copy-paste options (ALT+H+V+S) but you should generally stick with two: 'Paste as Values' (ALT+H+V+V) and 'Paste Formulas' (ALT+H+V+F). Here are my rules of thumb for copy-paste:

1. Never use straight copy-paste (i.e. CTRL+C and CTRL+V)
2. When copying from one input (blue font) cell to another, always use 'Paste as Values' (ALT+H+V+V)
3. When copying formulas over or down, always use 'Paste Formulas' (ALT+H+V+F)
4. When copying from one Workbook to another, only use 'Paste as Values'

## Circular References / Iterative Calculation

Avoiding circular references is essential to creating reliable, accurate, and transparent real estate financial models. While Excel allows iterative calculations to resolve circular references, enabling this feature introduces risks, including:

- Model Instability: Circular references can lead to infinite calculation loops or unpredictable behavior, especially in large or complex models. This instability may cause Excel to freeze, crash, or produce inconsistent results across systems.

- Calculation Inaccuracies: Iterative calculations rely on Excel approximating a solution based on user-defined settings, such as maximum iterations and precision thresholds. This can result in outputs that are close but not exact, and in some cases, far from the true value, depending on the complexity of the model.

- Difficulty in Debugging: Circular references obscure the audit trail of calculations, making it challenging to trace and fix errors. Any unintended circular reference can remain hidden, leading to unnoticed inaccuracies that ripple throughout the model.

At A.CRE, we avoid circular references and iterative calculations by employing alternative approaches, such as leveraging macros to handle complex calculations without resorting to iterative Excel settings.

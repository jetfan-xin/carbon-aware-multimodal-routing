# Historical code evidence

These two images were embedded in slide 13 of the final 2022 presentation. They are preserved without modifying their original content. English explanations are supplied here so the implementation can be understood without relying on the Chinese comments.

## Problem definition

![Historical Geatpy problem definition](problem-definition.png)

The fragment subclasses Geatpy's `Problem`, declares an integer-valued chromosome, configures a minimization objective and begins constructing route adjacency information. Helper functions and some referenced state are outside the screenshot.

## Decoding and objective evaluation

![Historical route decoding and fitness fragment](decoding-and-fitness.png)

The decoder maps a priority chromosome to a path and edge sequence. The visible fitness function iterates over the population, decodes each candidate, checks that its edges exist and accumulates edge costs. The decoder body is folded in the original screenshot.

These fragments support the use of Python, NumPy and Geatpy for a route problem. They do not by themselves demonstrate the complete final carbon-cost model, adaptive operators or uncertainty treatment. They are evidence images, not executable source files.

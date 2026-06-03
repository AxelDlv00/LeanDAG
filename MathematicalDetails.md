# Mathematical Details

## Directed Acyclic Graphs (DAGs)

* Let $P = \{P_1, \dots, P_n\}$ be a set of informal mathematical declarations (definitions, theorems, etc.). Let $H$ be a set of mathematical declarations that are already formalized (e.g., in Lean's Mathlib).
* We can generate a DAG, denoted as $\mathcal{G}$, from $(P, H)$ by introducing intermediate declarations $I$ and defining directed dependency edges between them.

## Measuring Progress

* For each node $s \in \mathcal{G}$, we define the **relative effort** $w_{\text{rel}}(s)$ as:

$$w_{\text{rel}}(s) = \begin{cases} 
0 & \text{if } \texttt{sorry} \notin \text{formal}(s) \wedge \text{formal}(s) \neq \varnothing \\ 
\ell(\text{informal}(s)) & \text{if } \text{informal}(s) \neq \varnothing \\ 
+\infty & \text{otherwise} 
\end{cases}$$



This represents the estimated formalization work remaining for $s$, independent of its dependencies. While the cost function $\ell$ can vary, a simple baseline choice is the character count of the informal text.
* For each node $s \in \mathcal{G}$, the **total effort** $w(s)$ accounts for dependencies and is defined as:

$$w(s) = \sum_{t \in \text{desc}^*(s)} w_{\text{rel}}(t)$$



where $\text{desc}^*(s)$ is the set of all unique descendants of $s$ (including $s$ itself). This metric estimates the cumulative formalization work required to fully verify $s$.

## Alternative Complexity Measures

* **Size-based metrics:** 
    * $\ell$ can represent the raw count of characters, tokens, or lines.
    * $\ell$ can represent a compressed or minimal length required to express the informal text.


* **AI-based metrics:**
    * $\ell$ can be an AI-predicted estimate of the character, token, or line count of the final *formal* code.
    * $\ell$ can be the estimated human time required to complete the formalization.

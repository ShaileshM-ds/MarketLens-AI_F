# Answer key: test-only, not included

The Demo generator writes a separate answer key that lists the scenarios it planted in the synthetic data. It is used only by automated tests, to check the analytics against known truth.

- It is **restricted to tests and evaluation** and must never be read by application analytics or used to tune them.
- It is **not copied into this pack**, and it must not be added to teammate import data.
- To reproduce it, run the Demo generator with the seed in `manifest.json`. The project keeps it apart from the data.

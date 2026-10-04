# Swarm Colosseum workshop: for teachers

One 90-minute lesson for students who have never written Python. Students play a strategy
game by writing the bots that play it: one side sends drones at a base, the other tries to
stop them. They run a match, read a short bot, change it, and watch what their change did
in a replay.

## Is it right for my class?

- **Level:** first-time programmers; no Python experience needed. Students who
  already know some Python get through all five exercises and can carry on with the
  extension at the end of the lesson plan.
- **Group size:** one laptop per student, or one between two (pairs work well).
- **What they practise:** reading code someone else wrote, dictionaries, `if` statements
  and lists, changing one thing at a time and testing it, and checking a guess against
  evidence. Every match can be replayed exactly, so "why did that happen?" always has an
  answer you can go and look at.
- **What it isn't:** it's not a simulation of anything real. The units are made up (`u`,
  `ticks`, `credits`), the map is blank, and nothing in it is real equipment, a real place
  or a real organisation. It's abstract on purpose, and that's the project's rule
  everywhere, not just in the workshop. The lesson plan has a short answer ready for the
  student who asks how it maps to the real world.

## What you need

- Python 3.11 on each laptop. No internet, no installs, no accounts, no Docker.
- A web browser to watch replays. They open as local files.
- A projector for the first ten minutes.
- Time the day before to copy the folder onto the laptops and run one check.

## The files, in the order you'll use them

| file | for | what's in it |
|---|---|---|
| `TEACHERS.md` | you, first | this page |
| [`FACILITATOR.md`](FACILITATOR.md) | you, the day before | setup, why running student code is safe here, common error messages, answers |
| [`LESSON_PLAN.md`](LESSON_PLAN.md) | you, on the day | the 90 minutes, minute by minute, with talking points |
| [`README.md`](README.md) | students | how to run a match, the rules on one screen, the five exercises |
| `starters/` | students | three attacker and three defender bots, each with one `# TODO` |
| `solutions/` | you only | one working answer per exercise; don't hand these out |

## Setting up, in three steps

1. Copy the folders listed at the top of `FACILITATOR.md` onto each laptop.
2. On one laptop, from the folder that holds `workshop/`, run `make workshop` (or
   `python workshop/check.py` on Windows). It must print `all exercises solvable`.
3. Run the first `play.py` command from `README.md` and open `my_match.html` in the
   browser. If you can see the replay, the room is ready.

## Safety, briefly

Each student runs only their own file, on their own laptop. Before running it, the
workshop tools apply the same checks the arena uses for every bot: only safe modules like
`math` and `random`, and no file access or running other programs. They also refuse
anything that isn't a single small `.py` file. Opponents are picked by name from the
game's built-in bots. `FACILITATOR.md` explains this in more detail. Tell students to run
only files they wrote themselves.

## After the lesson

Students keep their files. The public arena doesn't take outside bots yet. When it does,
`SUBMITTING.md` at the top of the repository will explain how. No licence has been chosen
for the project yet, so please check before you copy the materials beyond your own class.

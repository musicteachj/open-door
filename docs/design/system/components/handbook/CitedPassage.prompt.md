CitedPassage replaces the cited paragraph in the section body. Use it on the handbook page (with onClear) and in the PassagePanel (compact, no clear).

~~~jsx
<CitedPassage autoFocus onClear={() => navigate('/handbook/CA-4.3')}>
  You can use sick leave for your own illness, injury, or preventive care, or to care for a family member.
</CitedPassage>
~~~

On arrival from a deep link, the passage scrolls to the center of the view and takes focus; Clear highlight removes the ?passage parameter.
